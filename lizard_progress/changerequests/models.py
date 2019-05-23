# (c) Nelen & Schuurmans.  GPL licensed, see LICENSE.rst.
# -*- coding: utf-8 -*-

"""Models that handle change requests."""

# Python 3 is coming
from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import
from __future__ import division

import json
import logging

from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.core.urlresolvers import reverse
from django.contrib.gis.db import models
from django.contrib.sites.models import Site
from django.dispatch import receiver

from lizard_progress.util import geo
from lizard_progress import models as pmodels
from lizard_progress.email_notifications.models import NotificationType

logger = logging.getLogger(__name__)

# We have a few kinds of change requests;

# Requests are actual change requests. They come in several
# types. They can be open, accepted or refused. They have a
# motivation, enough information to be effected, and comments.

# Possible requests are generated by failed uploads. If the errors in
# the upload could possibly by fixed by requests, then the failures
# generate possible requests.  They need a bit more information from
# the uploader, and then they can be turned into real requests. If all
# possible requests are turned into real requests, and they are all
# accepted, the original uploaded file is re-submitted.


class Request(models.Model):
    adapter_class = 'adapter_changerequest'

    REQUEST_TYPE_REMOVE_CODE = 1
    REQUEST_TYPE_MOVE_LOCATION = 2
    REQUEST_TYPE_NEW_LOCATION = 3

    TYPES = {
        REQUEST_TYPE_REMOVE_CODE: "Locatiecode verwijderen",
        REQUEST_TYPE_MOVE_LOCATION: "Locatie verplaatsen",
        REQUEST_TYPE_NEW_LOCATION: "Nieuwe locatiecode",
    }

    REQUEST_STATUS_OPEN = 1
    REQUEST_STATUS_ACCEPTED = 2
    REQUEST_STATUS_REFUSED = 3
    REQUEST_STATUS_WITHDRAWN = 4
    REQUEST_STATUS_INVALID = 5

    STATUSES = {
        REQUEST_STATUS_OPEN: "Open",
        REQUEST_STATUS_ACCEPTED: "Geaccepteerd",
        REQUEST_STATUS_REFUSED: "Geweigerd",
        REQUEST_STATUS_WITHDRAWN: "Ingetrokken",
        REQUEST_STATUS_INVALID: "Ongeldig"
    }

    activity = models.ForeignKey(pmodels.Activity, null=True)

    request_type = models.IntegerField(choices=sorted(TYPES.items()))
    request_status = models.IntegerField(
        choices=sorted(STATUSES.items()), default=REQUEST_STATUS_OPEN)

    created_by_manager = models.BooleanField(default=False, null=False)

    refusal_reason = models.TextField(null=True, blank=True)
    invalid_reason = models.TextField(null=True, blank=True)

    creation_date = models.DateTimeField(auto_now_add=True)
    change_date = models.DateTimeField(auto_now=True)

    location_code = models.CharField(max_length=50)

    # Only used if this request is of type new location, in case an
    # optional old location will be removed.
    old_location_code = models.CharField(max_length=50, null=True, blank=True)

    # Note - a motivation is mandatory
    motivation = models.TextField()
    motivation_changed = models.DateTimeField(auto_now_add=True)

    # Seen is only used once requests are closed -- if not seen yet,
    # it is shown to the contractor in the recent changes list.
    seen = models.BooleanField(default=False)

    # Contains coordinates of the point. Used for new points, moved points,
    # as well as for showing points on the map.
    the_geom = models.PointField(null=True, srid=pmodels.SRID)

    @property
    def the_geomRD(self):
        g = self.the_geom
        g = g.transform(28992, clone=True)
        return g

    possible_request = models.ForeignKey(
        'PossibleRequest', null=True, blank=True,
        on_delete=models.SET_NULL)

    class Meta:
        ordering = ('creation_date',)

    def __unicode__(self):
        return (
            "{requesttype}: {codes} door {contractor} ({status})".format(
                requesttype=self.type_description,
                codes=(self.location_code +
                       (", vervangt " + self.old_location_code
                        if self.old_location_code else "")),
                contractor=self.activity.contractor,
                status=self.status_description))

    def adapter_layer_name(self):
        """Sort of a simplied Unicode."""
        return (
            "Aanvraag {requesttype} {codes} in {activity}".format(
                requesttype=self.type_description.lower(),
                codes=(self.location_code +
                       (", " + self.old_location_code
                        if self.old_location_code else "")),
                activity=self.activity))

    def get_absolute_url(self):
        return reverse('changerequests_detail', kwargs={
            'project_slug': self.activity.project.slug,
            'activity_id': self.activity.id,
            'request_id': str(self.id)})

    @property
    def project(self):
        return self.activity.project

    @property
    def type_description(self):
        return Request.TYPES.get(self.request_type, "Onbekend")

    @property
    def status_description(self):
        return Request.STATUSES.get(self.request_status, "Onbekend")

    @property
    def is_open(self):
        return self.request_status == Request.REQUEST_STATUS_OPEN

    @property
    def is_accepted(self):
        return self.request_status == Request.REQUEST_STATUS_ACCEPTED

    @property
    def is_refused(self):
        return self.request_status == Request.REQUEST_STATUS_REFUSED

    @property
    def is_invalid(self):
        return self.request_status == Request.REQUEST_STATUS_INVALID

    @property
    def is_valid(self):
        return not self.is_invalid

    def get_location(self, location_code=None):
        if location_code is None:
            location_code = self.location_code

        try:
            return pmodels.Location.objects.get(
                location_code=location_code,
                activity=self.activity)
        except pmodels.Location.DoesNotExist:
            return None

    def get_old_location(self):
        if not self.old_location_code:
            return None
        return self.get_location(self.old_location_code)

    def set_invalid(self, reason):
        self.invalid_reason = reason
        self.request_status = Request.REQUEST_STATUS_INVALID
        self.save()
        return False

    def _check_validity(self):
        """Return True if this change request is valid. Assumes request
        is open."""
        if self.request_type == Request.REQUEST_TYPE_REMOVE_CODE:
            # Location must exist, and this contractor can't have
            # measurements for it yet.
            location = self.get_location()
            if not location:
                return self.set_invalid("Locatie bestaat niet")
            if location.has_measurements():
                return self.set_invalid("Locatie heeft al metingen")

        elif self.request_type == Request.REQUEST_TYPE_MOVE_LOCATION:
            # Location must exist, and nobody can have uploaded measurements
            # for it yet
            location = self.get_location()
            if not location:
                return self.set_invalid("Locatie bestaat niet.")
            if location.has_measurements():
                return self.set_invalid("Locatie heeft al metingen.")
        elif self.request_type == Request.REQUEST_TYPE_NEW_LOCATION:
            # Location must NOT exist, and if an old_location is
            # given, it must exist and have no measurements for this
            # contractor yet.
            location = self.get_location()
            if location:
                return self.set_invalid("Locatie bestaat al.")

            if self.old_location_code:
                old_location = self.get_old_location()
                if not old_location:
                    return self.set_invalid("Oude locatie bestaat niet.")
                if old_location.has_measurements():
                    return self.set_invalid(
                        "Er zijn al metingen op de oude locatie.")

        return True

    def check_validity(self):
        """Returns True if this change request is still valid.

        If it is not, False is returned. This can be because the
        request is already closed (accepted, refused, withdrawn or
        invalid), in which case nothing more happens.

        If it was still open, the status of this request is also
        updated to invalid and the request is saved!"""
        if self.request_status != Request.REQUEST_STATUS_OPEN:
            return False

        return self._check_validity()

    def change_status(self, status):
        """Change status, save request, and handle possible side effects."""
        open_before = self.is_open

        self.request_status = status
        self.save()

    def accept(self):
        # Sanity check
        if not self.check_validity():
            return

        # Actually perform whatever this request wants
        if self.request_type == Request.REQUEST_TYPE_REMOVE_CODE:
            self.do_remove_code()
        elif self.request_type == Request.REQUEST_TYPE_MOVE_LOCATION:
            self.do_move_location()
        elif self.request_type == Request.REQUEST_TYPE_NEW_LOCATION:
            self.do_add_location()
            if self.old_location_code:
                self.do_remove_code(location_code=self.old_location_code)

        # Save new status
        self.change_status(Request.REQUEST_STATUS_ACCEPTED)

        if not self.created_by_manager:
            # Send notification. Requests by the manager are
            # auto-accepted, they don't want to receive mails in this
            # case.
            notification_type = NotificationType.objects.get(
                name='aanvraag geaccepteerd')
            kwargs = {
                'actor': pmodels.UserRole.objects.get(
                    code=pmodels.UserRole.ROLE_MANAGER),
                'action_object': self,
                'target': self.activity,
                'extra': {'link':
                          Site.objects.get_current().domain +
                          self.get_absolute_url()}
            }
            self.activity.notify_contractors(notification_type, **kwargs)

        if self.possible_request:
            # If all possible requests of a file are accepted, it
            # may be uploaded again
            self.possible_request.do_accept()

    def do_remove_code(self, location_code=None):
        location = self.get_location(location_code)
        location.delete()

    def do_move_location(self):
        """Apply a move request.

        Magic trick! This swaps the Request geom with the old geom of the
        Location object. Now the Location has the right (new) geom, and
        the Request has the old geom, so both can be showed on the map.
        """
        location = self.get_location()
        old_location_geom = location.the_geom
        location.the_geom = self.the_geom
        location.save()
        self.the_geom = old_location_geom
        self.save()

    def do_add_location(self):
        location, created = pmodels.Location.objects.get_or_create(
            location_code=self.location_code,
            activity=self.activity,
            defaults={'the_geom': self.the_geom, 'complete': False})

    def refuse(self, reason):
        self.refusal_reason = reason
        self.change_status(Request.REQUEST_STATUS_REFUSED)

        # Send notification
        notification_type = NotificationType.objects.get(
            name="aanvraag afgekeurd")
        kwargs = {
            'actor': pmodels.UserRole.objects.get(
                code=pmodels.UserRole.ROLE_MANAGER),
            'action_object': self,
            'target': self.activity,
            'extra': {'link':
                      Site.objects.get_current().domain +
                      self.get_absolute_url()}}
        self.activity.notify_contractors(notification_type, **kwargs)

    def withdraw(self):
        self.change_status(Request.REQUEST_STATUS_WITHDRAWN)

    def did_last_action(self, organization=None):
        """Did this organization do the last action related to this request?
        Then we don't have to show an alert to them.

        There are a few actions: comments, opening the request,
        closing the request, changing the motivation. In case of
        closing, invalid was caused elsewhere so we return False;
        withdrawing is done by the contractor, otherwise closing is
        done by the project owner. Comments are done by a specific
        organization. They have to be compared with the last change of
        the motivation. Opening also involves setting a motivation.

        If organization is None, use self.view.organization (view is set by
        the view's open_requests method)."""

        if organization is None:
            organization = self.view.organization

        if not self.is_open:
            if self.request_status == Request.REQUEST_STATUS_INVALID:
                return False  # Invalid was caused elsewhere
            elif self.request_status in (
                    Request.REQUEST_STATUS_ACCEPTED,
                    Request.REQUEST_STATUS_REFUSED):
                return organization == self.activity.project.organization
            elif self.request_status == Request.REQUEST_STATUS_WITHDRAWN:
                return organization == self.activity.contractor

        # Laatste comment
        comments = list(self.requestcomment_set.all())

        if comments:
            comment = comments[-1]

            profile = pmodels.UserProfile.get_by_user(comment.user)
            return profile.organization == organization

        # No comments, open -- last action is assumed to be by the
        # contractor
        return organization == self.activity.contractor

    @classmethod
    def open_requests(cls):
        return cls.objects.filter(
            request_status=Request.REQUEST_STATUS_OPEN).select_related()

    @classmethod
    def closed_requests(cls):
        return cls.objects.exclude(
            request_status=Request.REQUEST_STATUS_OPEN).select_related()

    def can_see(self, profile):
        """Return True if profile is allowed to see this request."""
        if (profile.has_role(pmodels.UserRole.ROLE_MANAGER) and
                self.activity.project.organization == profile.organization):
            return True

        if profile.has_role(pmodels.UserRole.ROLE_UPLOADER):
            return self.activity.contractor == profile.organization

        return False

    @classmethod
    def open_requests_for_profile(cls, activity, profile, project=None):
        """Return open requests for a profile, per activity or optionally
        per project (for the map page). If a project is given, activity
        is ignored."""

        if project is not None:
            qs = cls.open_requests().filter(activity__project=project)
        else:
            qs = cls.open_requests().filter(activity=activity)

        return [
            request for request in qs
            if request.check_validity() and request.can_see(profile)]

    @classmethod
    def closed_requests_for_profile(cls, activity, profile):
        return [
            request for request in
            cls.closed_requests().filter(activity=activity)
            if request.can_see(profile)]

    def adapter_layer_json(self):
        return json.dumps({
            'changerequest_id': self.id})

    def record_comment(self, user, comment):
        RequestComment.objects.create(
            request=self, comment=comment, user=user)

    def zoom_extent(self):
        """Return our the_geom as a (minx, miny, maxx, maxy) tuple.

        For speed reasons, we don't care about the coordinates
        of the existing Location our location_code refers to; the extent
        of those is usually already known anyway."""
        if not self.the_geom:
            return None

        x = self.the_geom.x
        y = self.the_geom.y

        return (x, y, x, y)

    @classmethod
    def create_deletion_request(
            cls, location, motivation, user_is_manager, geom=None):
        request, created = cls.objects.get_or_create(
            activity=location.activity,
            request_type=cls.REQUEST_TYPE_REMOVE_CODE,
            request_status=cls.REQUEST_STATUS_OPEN,
            location_code=location.location_code, defaults=dict(
                created_by_manager=user_is_manager,
                motivation=motivation,
                the_geom=geo.osgeo_3d_point_to_2d_wkt(
                    geom if geom is not None else location.the_geom)))
        return request


class RequestComment(models.Model):
    """Comments connected to some request."""
    request = models.ForeignKey(Request)
    user = models.ForeignKey(User)
    comment = models.TextField()
    comment_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('comment_time',)

    def __unicode__(self):
        return (
            "{u}@{d}: {c}"
            .format(u=self.user, d=self.comment_time, c=self.comment))


class PossibleRequest(models.Model):
    """This is attached to an uploaded file, and created by a parser
    that runs into an error. If the error could be fixed with an
    accepted request, then the parser can create a
    PossibleRequest. The user can give a motivation to turn it into a
    real request.

    There are two possible possible requests: for new location and for
    moved location."""

    uploaded_file = models.ForeignKey(pmodels.UploadedFile)
    requested = models.BooleanField(default=False)
    accepted = models.BooleanField(default=False)

    request_type = models.IntegerField(choices=sorted(Request.TYPES.items()))
    location_code = models.CharField(max_length=50)
    # Contains coordinates of the point.
    the_geom = models.PointField(null=True, srid=pmodels.SRID)

    class Meta:
        ordering = ('location_code',)

    def __unicode__(self):
        return "PossibleRequest(uploaded_file={u}, location_code={l})".format(
            u=self.uploaded_file_id, l=self.location_code)

    def request(self):
        if self.requested:
            try:
                return Request.objects.get(
                    possible_request=self)
            except Request.DoesNotExist:
                return None
        else:
            return None

    def do_accept(self):
        """Called if this possible request was accepted. If the
        related uploaded file was fixable (all its errors had possible
        requests) and all of the possible requests were done and
        accepted, then re-upload the file."""
        self.accepted = True
        self.save()

        if not self.uploaded_file.is_fixable():
            return

        if self.uploaded_file.possiblerequest_set.filter(
                accepted=False).count() == 0:
            self.uploaded_file.re_upload()

    def activate(self, motivation, old_location_code=None):
        """Turn this possible request into an actual request. Return
        None on success. If a request for this location already exists,
        return an error message."""

        try:
            location = pmodels.Location.objects.get(
                activity=self.uploaded_file.activity,
                location_code=self.location_code)
            if location.has_measurements():
                return "Kan aanvraag niet doen, de locatie heeft al metingen."
        except pmodels.Location.DoesNotExist:
            pass

        # We need to do two tests to see if it already exists: on
        # location_code and on old_location_code. Requesting also
        # fails if another contractor has already done a request for
        # this code, such is life. Can be made one query with Q
        # objects, but I'm pressed for time.
        if (Request.objects.filter(
                activity=self.uploaded_file.activity,
                request_status=Request.REQUEST_STATUS_OPEN,
                location_code=self.location_code).exists() or
            Request.objects.filter(
                activity=self.uploaded_file.activity,
                request_status=Request.REQUEST_STATUS_OPEN,
                old_location_code=self.location_code).exists()):
            return "Er is al een open aanvraag voor deze locatie."

        Request.objects.create(
            activity=self.uploaded_file.activity,
            request_status=Request.REQUEST_STATUS_OPEN,
            location_code=self.location_code,
            request_type=self.request_type,
            old_location_code=old_location_code,
            motivation=motivation,
            the_geom=self.the_geom,
            possible_request=self)

        self.requested = True
        self.save()
        return None

    @classmethod
    def create_from_dict(cls, uploaded_file, possible_request):
        """Create a new PossibleRequest based on a dictionary returned
        by a parser."""

        cls.objects.create(
            uploaded_file=uploaded_file,
            request_type=possible_request['request_type'],
            location_code=possible_request['location_code'],
            the_geom='POINT({x} {y})'.format(**possible_request))


class Points(models.Model):
    """Complete dummy class that's only here to work around a Mapnik
    bug in layers.py."""
    location_code = models.CharField(max_length=50)
    dx = models.IntegerField()
    dy = models.IntegerField()
    the_geom = models.PointField(srid=pmodels.SRID)

    @classmethod
    def points_around(cls, location_code, the_geom, e=0.001):
        x, y = the_geom.x, the_geom.y

        for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1), (0, 0)):
            xx = x + dx * e
            yy = y + dy * e
            geom = 'POINT({} {})'.format(xx, yy)
            point, created = cls.objects.get_or_create(
                location_code=location_code,
                dx=dx, dy=dy, defaults=dict(
                    the_geom=geom))
            if not created:
                point.the_geom = geom
                point.save()


@receiver(post_save, sender=Request)
def message_request_created(sender, instance, created, **kwargs):
    notification_type = NotificationType.objects.get(name="aanvraag ingediend")

    if instance.created_by_manager:
        return  # Don't send mail if request was created by manager.

    if not created:
        # I don't know how this is possible, but let's check it...
        return

    actor = pmodels.UserRole.objects.get(code=pmodels.UserRole.ROLE_UPLOADER)
    instance.activity.notify_managers(
        notification_type, actor=actor, action_object=instance,
        target=instance.activity, extra={
            'link': Site.objects.get_current().domain +
            instance.get_absolute_url()})


@receiver(post_save, sender=RequestComment)
def message_request_comment_created(sender, instance, created, **kwargs):
    notification_type = NotificationType.objects.get(
        name="aanvraag commentaar toegevoegd")
    kwargs = {
        'actor': instance.user,
        'action_object': instance.request,
        'target': instance.request.activity,
        'extra': {'link':
                  Site.objects.get_current().domain +
                  instance.request.get_absolute_url()}
    }
    if created:
        if instance.request.activity.project.is_manager(instance.user):
            instance.request.activity.notify_contractors(
                notification_type, **kwargs)
        else:
            instance.request.activity.notify_managers(
                notification_type, **kwargs)
