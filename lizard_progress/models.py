# (c) Nelen & Schuurmans.  GPL licensed, see LICENSE.txt.
# from django.db import models

RDNEW = 28992
SRID = RDNEW

import logging
import os

from django.contrib.gis.db import models
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse

from lizard_map.models import JSONField

import lizard_progress.specifics

logger = logging.getLogger(__name__)


def has_access(user, project, contractor=None):
    """Test whether user has access to this project (showing data of
    this contractor.

    Should probably be implemented using lizard-security but I lack
    the time to figure that out right now."""

    if user.is_anonymous():
        # Not logged in
        return False

    if user.is_superuser:
        # Site superuser
        return True

    if project.superuser == user:
        # Project superuser
        return True

    if contractor:
        return contractor.user == user
    else:
        # If this is not about some specific contractor's data,
        # all contractors have access.
        for c in project.contractor_set.all():
            if c.user == user:
                return True

    return False


class Project(models.Model):
    # "Profielen", "Peilschalen", etc
    name = models.CharField(max_length=50)
    slug = models.SlugField(max_length=50, unique=True)
    superuser = models.ForeignKey(User, null=True, blank=True)

    def __unicode__(self):
        return unicode(self.name)

    def specifics(self):
        logger.debug("Asking for specifics...")
        return lizard_progress.specifics.specifics(self)


class Contractor(models.Model):
    # "Tijhuis", "Van der Zwaan", etc
    project = models.ForeignKey(Project)
    name = models.CharField(max_length=50)
    slug = models.SlugField(max_length=50)
    user = models.ForeignKey(User, null=True, blank=True)

    def __unicode__(self):
        return u"%s in %s" % (self.name, self.project.name)


class Area(models.Model):
    # "Noord", "Oost", "Zuid", "West", ...
    project = models.ForeignKey(Project)
    name = models.CharField(max_length=50)
    slug = models.CharField(max_length=50)

    def __unicode__(self):
        return u"%s in %s" % (self.name, self.project.name)


class Location(models.Model):
    # All relevant locations in the project
    unique_id = models.CharField(max_length=50, primary_key=True)

    project = models.ForeignKey(Project)
    area = models.ForeignKey(Area, null=True, blank=True)

    the_geom = models.PointField(null=True, srid=SRID)
    # Any extra known information about the location
    information = JSONField(null=True, blank=True)

    objects = models.GeoManager()

    class Meta:
        # IDs are unique within a project
        unique_together = (("unique_id", "project"))

    def __unicode__(self):
        return u"Location with id '%s'" % (self.unique_id,)


class MeasurementType(models.Model):
    # "Dwarsprofiel", "Oeverfoto", "Oeverkenmerk", "Peilschaal foto",
    # "Peilschaal kenmerk"
    project = models.ForeignKey(Project)
    name = models.CharField(max_length=50)
    slug = models.SlugField(max_length=50)

    icon_missing = models.CharField(max_length=50, null=True, blank=True)
    icon_complete = models.CharField(max_length=50, null=True, blank=True)
    global_icon_complete = models.CharField(
        max_length=50, null=True, blank=True)

    def __unicode__(self):
        return u"Type '%s' in %s" % (self.name, self.project.name)


class ScheduledMeasurement(models.Model):
    project = models.ForeignKey(Project)
    contractor = models.ForeignKey(Contractor)
    measurement_type = models.ForeignKey(MeasurementType)
    location = models.ForeignKey(Location)
    timestamp = models.DateTimeField(auto_now=True)

    complete = models.BooleanField()

    @property
    def measurement(self):
        """Note: ONLY use this if you are sure there will be only a single
        measurement object per scheduledmeasurement object you call this on.
        It makes no sense in other situations.

        Returns None if there is no measurement. If there are multiple
        measurements, MultipleObjectsReturned is raised."""
        try:
            return Measurement.objects.get(scheduled=self)
        except Measurement.DoesNotExist:
            return None


class Measurement(models.Model):
    """Although most ScheduledMeasurements will have only a single
    associated measurements, some will have more because there is only
    a single file associated with a measurements.

    E.g. HDSR's Dwarsprofielen project has a measurement type "fotos"
    that calls for two photos, one of the left bank and one of the
    right bank. That must be represented by two measurements, since
    there are two different files. However, there is only one
    scheduled measurement."""

    scheduled = models.ForeignKey(ScheduledMeasurement)

    # Dict with the data.
    # Site decides what to store.
    data = JSONField(null=True)

    # The date as retrieved from the measurement data, not the date of
    # uploading.
    date = models.DateTimeField(null=True, blank=True)

    # Any available geometry data in the uploaded measurement.
    the_geom = models.PointField(null=True, blank=True, srid=SRID)

    # This is the filename of the uploaded file after it was moved
    # into lizard-progress' archive. Set by the upload view.
    filename = models.CharField(max_length=1000)

    # Auto-changes, most likely set in stone the time the file is
    # uploaded.
    timestamp = models.DateTimeField(auto_now=True)

    objects = models.GeoManager()

    @property
    def url(self):
        """Return the URL to the uploaded file that contained this
        measurement."""
        
        sm = self.scheduled
        return reverse('lizard_progress_filedownload', kwargs={
                    'project_slug': sm.project.slug,
                    'contractor_slug': sm.contractor.slug,
                    'measurement_type_slug': sm.measurement_type.slug,
                    'filename': os.path.basename(self.filename)})