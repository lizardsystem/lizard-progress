# (c) Nelen & Schuurmans. GPL licensed, see LICENSE.txt.

"""Views concerned with downloading files."""

import logging
import os
import platform

from django.conf import settings
from django.core.urlresolvers import reverse
from django import http
from django.http import HttpResponse
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.views.generic import View
from django.views.static import serve

from lizard_ui.layout import Action

from lizard_progress import models
from lizard_progress import tasks
from lizard_progress.util import directories

from lizard_progress.models import Project
from lizard_progress.models import has_access
from lizard_progress.models import Organization
from lizard_progress.views.views import ProjectsView

logger = logging.getLogger(__name__)


APP_LABEL = Project._meta.app_label


class DownloadOrganizationDocumentView(View):

    def get(self, request, organization_id, filename):
        organization = get_object_or_404(Organization,
                                         id=organization_id)

        directory = directories.organization_files_dir(
            organization)

        path = os.path.join(directory, filename)

        if not os.path.exists(path):
            raise http.Http404()

        return serve(request, path, '/')

    @models.UserRole.check(models.UserRole.ROLE_MANAGER)
    def delete(self, request, organization_id, filename):
        """Delete a downloadable file."""
        organization = get_object_or_404(Organization,
                                         id=organization_id)

        directory = directories.organization_files_dir(
            organization)
        path = os.path.join(directory, filename)

        if os.path.exists(path) and os.path.isfile(path):
            os.remove(path)
        else:
            raise http.Http404()

        return HttpResponse()


class DownloadDocumentsView(ProjectsView):
    template_name = "lizard_progress/documents_download.html"

    def _make_url(self, filetype, path):
        return reverse('lizard_progress_download_organization_document',
                       kwargs={
                           'organization_id': self.organization.id,
                           'filename': os.path.basename(path)
                       })

    def _organization_files(self):
        for path in directories.files_in(
                directories.organization_files_dir(self.organization)):
            yield {
                'type': 'Handleidingen e.d.',
                'filename': os.path.basename(path),
                'size': directories.human_size(path),
                'url': self._make_url('organization', path)
                }

    def files(self):
        if not hasattr(self, '_files'):
            def sorted_on_filename(iterable):
                return sorted(
                    iterable,
                    key=lambda f: f.get('filename', '').lower())

            try:
                self._files = {
                    'organization': sorted_on_filename(
                        self._organization_files()),
                    }
            except Exception as e:
                logger.debug(e)
        return self._files


class DownloadHomeView(ProjectsView):
    """This view offers links to downloadable project artifacts.

    If the user does not have sufficient rights,
    a `HttpResponseForbidden` is returned.
    """
    template_name = "lizard_progress/download_home.html"
    active_menu = "download"

    def _make_url(self, filetype, project, activity, path):
        return reverse('lizard_progress_downloadview', kwargs={
            'filetype': filetype,
            'project_slug': project.slug,
            'activity_id': activity.id if activity else '0',
            'filename': os.path.basename(path)
        })

    def _project_files(self):
        for path in directories.files_in(
                directories.project_files_dir(self.project)):
            yield {
                'type': 'Handleidingen e.d.',
                'filename': os.path.basename(path),
                'size': directories.human_size(path),
                'url': self._make_url('organization',
                                      self.project,
                                      None,
                                      path)
                }

    def _reports_files(self):
        for activity in self.project.activity_set.all():
            if has_access(self.user, self.project, activity.contractor):
                for path in directories.files_in(
                        directories.reports_dir(activity)):
                    yield {
                        'type': 'Rapporten {}'.format(activity),
                        'filename': os.path.basename(path),
                        'size': directories.human_size(path),
                        'url': self._make_url('reports',
                                              self.project,
                                              activity,
                                              path)
                    }

    def _results_files(self):
        for activity in self.project.activity_set.all():
            if has_access(self.user, self.project, activity.contractor):
                for path in directories.files_in(
                        directories.results_dir(activity)):
                    yield {
                        'type': 'Resultaten {}'.format(activity),
                        'filename': os.path.basename(path),
                        'size': directories.human_size(path),
                        'url': self._make_url(
                            'results', self.project,
                            activity, path)
                        }

    def _shapefile_files(self):
        for activity in self.project.activity_set.all():
            if has_access(self.user, self.project, activity.contractor):
                for path in directories.all_files_in(
                        directories.shapefile_dir(activity)):
                    yield {
                        'type': 'Ingevulde hydrovakken shapefile {}'
                        .format(activity.contractor.name),
                        'filename': os.path.basename(path),
                        'size': directories.human_size(path),
                        'url': self._make_url(
                            'contractor_hydrovakken', self.project,
                            activity, path)
                    }

    def _hydrovakken_files(self):
        if has_access(self.user, self.project):
            for path in directories.all_files_in(
                directories.hydrovakken_dir(self.project),
                    extension=".shp"):
                yield {
                    'description':
                    "Hydrovakken {project}".format(project=self.project),
                    'urls': {
                        'shp': self._make_url(
                            'hydrovakken', self.project, None, path),
                        'dbf': self._make_url(
                            'hydrovakken', self.project, None,
                            path.replace('.shp', '.dbf')),
                        'shx': self._make_url(
                            'hydrovakken', self.project, None,
                            path.replace('.shp', '.shx'))
                    }}

    def files(self):
        if not hasattr(self, '_files'):
            def sorted_on_filename(iterable):
                return sorted(
                    iterable,
                    key=lambda f: f.get('filename', '').lower())

            try:
                self._files = {
                    'organization': sorted_on_filename(
                        self._project_files()),
                    'reports': sorted_on_filename(self._reports_files()),
                    'results': sorted_on_filename(self._results_files()),
                    'contractor_hydrovakken': sorted_on_filename(
                        self._shapefile_files()),
                    'hydrovakken': sorted_on_filename(
                        self._hydrovakken_files()),
                    }
            except Exception as e:
                logger.debug(e)
        return self._files

    def csv(self):
        """Links to CSV downloads. One per activity."""

        if hasattr(self, '_csvs'):
            return self._csvs

        csvs = []

        for activity in self.project.activity_set.all():
            if has_access(
                    self.request.user, self.project, activity.contractor):
                url = reverse(
                    'lizard_progress_dashboardcsvview',
                    kwargs={
                        'project_slug': self.project_slug,
                        'activity_id': activity.id
                        })

                csvs.append((activity, url))

        self._csvs = csvs
        return csvs

    def exports(self):
        return [
            exportrun
            for exportrun in models.ExportRun.all_in_project(
                self.project, self.request.user)
            ]

    @property
    def breadcrumbs(self):
        """Breadcrumbs for this page."""
        crumbs = super(DownloadHomeView, self).breadcrumbs

        crumbs.append(
            Action(
                description=("Downloads for {project}"
                             .format(project=self.project.name)),
                name="Download",
                url=reverse(
                    'lizard_progress_downloadhomeview',
                    kwargs={'project_slug': self.project_slug})))

        return crumbs

    @staticmethod
    def upload_dialog_url():
        """Returns URL to the file upload dialog."""
        return reverse('lizard_progress_uploaddialogview')


class DownloadView(View):
    """Downloading files."""

    def get(self, request, filetype, project_slug,
            activity_id, filename):
        project = get_object_or_404(Project, slug=project_slug)

        if activity_id != '0':
            activity = get_object_or_404(models.Activity, pk=activity_id)
        else:
            activity = None

        if not has_access(
                request.user, project,
                activity.contractor if activity else None):
            return HttpResponseForbidden()

        if filetype == 'reports':
            directory = directories.reports_dir(activity)
        elif filetype == 'results':
            directory = directories.reports_dir(activity)
        elif filetype == 'organization':
            directory = directories.project_files_dir(project)
        elif filetype == 'hydrovakken':
            directory = directories.hydrovakken_dir(project)
            for path in directories.all_files_in(directory):
                if os.path.basename(path) == filename:
                    directory = os.path.dirname(path)
                    break
            else:
                raise http.Http404()
        elif filetype == 'contractor_hydrovakken':
            directory = directories.shapefile_dir(activity)
            for path in directories.all_files_in(directory):
                if os.path.basename(path) == filename:
                    directory = os.path.dirname(path)
                    break
            else:
                raise http.Http404()
        else:
            return HttpResponseForbidden()

        path = os.path.join(directory, filename)

        if not os.path.exists(path):
            raise http.Http404()

        return serve(request, path, '/')

    def delete(self, request, filetype, project_slug,
               activity_id, filename):
        """Delete a downloadable file. For now, only for files without
        activity ('organization files')."""

        if activity_id != '0' or filetype != 'organization':
            return HttpResponseForbidden()

        project = get_object_or_404(Project, slug=project_slug)

        if not project.is_manager(request.user):
            return HttpResponseForbidden()

        directory = directories.project_files_dir(project)
        path = os.path.join(directory, filename)
        if os.path.exists(path) and os.path.isfile(path):
            os.remove(path)
        else:
            raise http.Http404()

        return HttpResponse()


def start_export_run_view(request, project_slug, export_run_id):
    if request.method != "POST":
        logger.debug("method is not POST, but {0}".format(request.method))
        return HttpResponseForbidden()

    try:
        export_run = models.ExportRun.objects.get(pk=export_run_id)
    except models.ExportRun.DoesNotExist:
        logger.debug("No such export run")
        return HttpResponseForbidden()

    if export_run.activity.project.slug != project_slug:
        logger.debug("Wrong project slug")
        return HttpResponseForbidden()

    if not models.has_access(
            request.user, export_run.activity.project,
            export_run.activity.contractor):
        logger.debug("No access")
        return HttpResponseForbidden()

    # Clear existing export
    export_run.clear()
    export_run.export_running = True
    export_run.save()

    # Start the Celery task
    tasks.start_export_run.delay(export_run.id, request.user)

    return HttpResponse()


def protected_download_export_run(request, project_slug, export_run_id):
    """
    Copied from views.protected_file_download, see there.
    No Apache support, only Nginx.
    """

    try:
        export_run = models.ExportRun.objects.get(pk=export_run_id)
    except models.ExportRun.DoesNotExist:
        return HttpResponseForbidden()

    if export_run.activity.project.slug != project_slug:
        return HttpResponseForbidden()

    if not has_access(
            request.user, export_run.activity.project,
            export_run.activity.contractor):
        return HttpResponseForbidden()

    file_path = export_run.file_path
    logger.debug("File path: " + file_path)

    nginx_path = '/'.join([
        '/protected', 'export',
        export_run.activity.project.organization.name,
        os.path.basename(file_path)])

    # This is where the magic takes place.
    response = HttpResponse()
    response['X-Accel-Redirect'] = nginx_path  # Nginx

    # Unset the Content-Type as to allow for the webserver
    # to determine it.
    response['Content-Type'] = ''

    # Only works for Apache and Nginx, under Linux right now
    if settings.DEBUG or not platform.system() == 'Linux':
        return serve(request, file_path, '/')
    return response
