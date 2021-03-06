"""Machinery to give actual .MET files to the MET parser, to see if it
returns the expected errors."""


import mock

from pkg_resources import resource_filename

from nose.plugins.attrib import attr

from lizard_progress import models
from lizard_progress import process_uploaded_file
from lizard_progress.tests import test_models
from lizard_progress.tests.base import FixturesTestCase


def create_org_and_user(orgname, username, is_project_owner):
    organization = test_models.OrganizationF.create(
        name=orgname,
        is_project_owner=is_project_owner)

    user = test_models.UserF.create(username=username, is_superuser=False)
    test_models.UserProfileF.create(user=user, organization=organization)

    return organization, user


def dwarsprofiel_available_mtype():
    amt, created = models.AvailableMeasurementType.objects.get_or_create(
        slug="dwarsprofiel", defaults=dict(
            name="Dwarsprofiel",
            slug="dwarsprofiel",
            needs_predefined_locations=False,
            likes_predefined_locations=True,
            needs_scheduled_measurements=False,
            implementation=''
        ))
    return amt


class TestOrganization(FixturesTestCase):
    """No actual tests in this, just helper functions. Subclasses
    below for Waternet, etc."""
    def get_errors(self, uploaded_file):
        return list(uploaded_file.uploadedfileerror_set.all())

    def setup_uploaded_file(self, path):
        uploaded_file = test_models.UploadedFileF.create(
            activity=self.activity,
            uploaded_by=self.upload_user,
            rel_file_path=path)
        return uploaded_file

    def try_file(self, filename, expected_errors=None):
        """Expected_errors is an iterable of (line, error_code) pairs.

        If expected_errors is None, ignore errors, just check that the
        parser runs without trouble.

        If expected_errors is True, check that there are errors, but
        don't care which.

        Otherwise, expected_errors is an iterable.

        If expected_errors is empty, check that the parse is
        successful.

        Otherwise, assert that at least all expected_errors are
        present. There may be more."""

        path = resource_filename(
            'lizard_progress',
            'tests/test_met_files/' + filename)
        uploaded_file = self.setup_uploaded_file(path)
        process_uploaded_file.process_uploaded_file(uploaded_file.id)
        errors = set(
            (error.line, error.error_code)
            for error in self.get_errors(uploaded_file))

        # Process_uploaded_file gets a fresh instance from the database, so
        # our old one isn't updated
        uploaded_file = models.UploadedFile.objects.get(
            pk=uploaded_file.id)

        # Helpful in case this fails
        print(path)
        print(expected_errors)
        print(errors)

        if expected_errors is None:
            return

        if expected_errors is True:
            self.assertFalse(uploaded_file.success)
            self.assertTrue(len(errors) > 0)
        elif not expected_errors:
            self.assertTrue(uploaded_file.success)
            self.assertEquals(len(errors), 0)
        else:
            self.assertFalse(uploaded_file.success)
            self.assertTrue(len(errors) >= len(expected_errors))
            for error in expected_errors:
                self.assertTrue(error in errors)


@attr('slow')  # Exclude these with bin/test '-a!slow'
@mock.patch('shutil.move')  # So that the file isn't moved for real in the end
class TestHDSR(TestOrganization):
    def setUp(self):
        super(TestHDSR, self).setUp()

        self.project_org, self.project_user = create_org_and_user(
            'HDSR', 'hdsr', True)

        self.project_org.set_error_codes((
            'MET_XY_OCCURS_ONCE_IN_PROFILE',
        ))

        self.upload_org, self.upload_user = create_org_and_user(
            'Testuploader', 'test', False)

        self.project = test_models.ProjectF.create(
            organization=self.project_org,
            name="testprojecthdsr",
            slug="testprojecthdsr")

        self.organization = test_models.OrganizationF.create(
            name="contractorhdsr")

        self.mtype = dwarsprofiel_available_mtype()

        self.activity = test_models.ActivityF.create(
            project=self.project, name="activityhdsr",
            contractor=self.organization,
            measurement_type=self.mtype)

    def test_xy_occurs_only_once(self, *args):
        self.try_file(
            'hdsr/1 XY komt meerdere keren voor.met',
            set([(20, 'MET_XY_OCCURS_ONCE_IN_PROFILE')]))


@attr('slow')  # Exclude these with bin/test '-a!slow'
@mock.patch('shutil.move')  # So that the file isn't moved for real in the end
class TestWaternet(TestOrganization):
    def setUp(self):
        super(TestWaternet, self).setUp()

        self.project_org, self.project_user = create_org_and_user(
            'Waternet', 'waternet', True)

        self.project_org.set_error_codes((
            'NO_LOCATION',
            'MET_NAP',
            'MET_ABS',
            'MET_PEILWAARDENUL',
            'MET_TWOZVALUES',
            'MET_PROFILETYPEPLACING_XY',
            'MET_2MEASUREMENTS',
            'MET_ONE_1_CODE',
            'MET_ONE_2_CODE',
            'MET_TWO_22_CODES',
            'MET_ONE_7_CODE',
            'MET_EXPECTED_CODE_2',
            'MET_EXPECTED_CODE_1',
            'MET_EXPECTED_CODE_1_OR_2',
            'MET_CODE_7_IN_BETWEEN_22',
            'MET_WRONG_PROFILE_POINT_TYPE',
            'MET_UNDERSCORE_IN_PROFILE_ID',
            'MET_SERIES_ID_IN_PROFILE_ID',
            'MET_PROFILE_NUMBER_IN_DESC',
            'MET_AT_LEAST_ONE_5_CODE',
            'MET_AT_LEAST_ONE_6_CODE',
            'MET_XY_METING_IS_PROFILE',
            'MET_DIFFERENCE_Z1Z2_MAX_1M',
            'MET_XY_STRICT_ASCDESC',
            'MET_Z1GREATERTHANZ2',
#                'MET_XY_ASCDESC_1CM'
        ))

        self.upload_org, self.upload_user = create_org_and_user(
            'Testuploader', 'test', False)

        self.project = test_models.ProjectF.create(
            organization=self.project_org,
            name="testprojectwaternet",
            slug="testprojectwaternet")

        self.organization = test_models.OrganizationF.create(
            name="contractorwaternet")

        self.mtype = dwarsprofiel_available_mtype()

        self.activity = test_models.ActivityF.create(
            project=self.project, name="activitywaternet",
            contractor=self.organization,
            measurement_type=self.mtype)

    def test_correct_file(self, *args):
        pass
        # Disabled -- it fails because locations aren't defined.
        #self.try_file(
        #    'waternet/a/Metfile_Goed.met',
        #    set())

    def test_versienummer_correct(self, *args):
        self.try_file(
            'waternet/a/1 Versienummer_correct.met',
            set([(1, 'MET_WRONGVERSION')]))

    def test_versienummer_aanwezig(self, *args):
        self.try_file(
            'waternet/a/1 Versienummer_aanwezig.met',
            set([
                (1, 'MET_NOVERSION')
            ]))

    def test_reeks_opmaak(self, *args):
        self.try_file(
            'waternet/a/2 Reeksheader_opmaak.met',
            set([
                (2, 'MET_REEKSELEMENTS')
            ]))

    def test_reeks_aanwezig(self, *args):
        self.try_file(
            'waternet/a/2 Reeksnaam_aanwezig.met',
            set([
                (2, 'MET_REEKSNOTFOUND')
            ]))

    def test_haken_aanwezig(self, *args):
        self.try_file(
            'waternet/a/3 Haken_aanwezig_regel.met',
            set([
                (4, 'MET_METINGLINEWRONG'),
                (19, 'MET_METINGLINEWRONG'),
                (26, 'MET_METINGLINEWRONG'),
                (30, 'MET_METINGLINEWRONG')
            ]))

    def test_komma_datascheiding(self, *args):
        self.try_file(
            'waternet/a/4 Komma_datascheiding.met',
            set([
                (4, 'MET_METINGSIXVALUES'),
                (25, 'MET_METINGSIXVALUES'),
                (36, 'MET_METINGSIXVALUES')
            ]))

    def test_punt_decimaalscheiding(self, *args):
        self.try_file(
            'waternet/a/4 Punt_decimaalscheiding.met',
            set([
                (4, 'MET_METINGSIXVALUES'),
                (26, 'MET_METINGSIXVALUES'),
            ]))

    def test_scheiding_duizendtallen(self, *args):
        self.try_file(
            'waternet/a/7 Scheidingsteken_duizendtallen.met',
            set([
                (4, 'MET_METINGSIXVALUES'),
            ]))

    def test_poging_remco(self, *args):
        self.try_file(
            'waternet/b/4x Vierde element poging Remco.met',
            set([
                (3, 'MET_PROFIELELEMENTS'),
            ]))

    def test_correct_files(self, *args):
        filenames = (
            # 'waternet/b/Metfile_Goed.met', # FAILS
            )

        for filename in filenames:
            self.try_file(filename, set())

    def test_other_erroring_files(self, *args):
        filenames = (
            # 'waternet/b/1 Reeksnummer_aanwezig.met',
            # 'waternet/b/2 Profielnummer_aanwezig_correct.met',
            # 'waternet/b/3 Underscore_profiel_archiefnummer.met',
            # 'waternet/b/4a Vierde_element_0.met',
            # 'waternet/b/4b Vijfde_element_NAP.met',
            # 'waternet/b/4c Zesde_element_ABS.met',
            # 'waternet/b/4d Zevende_element_2.met',
            # 'waternet/b/4e Achtste_element_XY.met',
            # 'waternet/b/5 Coordinaat_startpunt_meetpunt1_gelijk.met',
            # 'waternet/c/1 Aantal_profielcodes.met',
            # 'waternet/c/2 Overige_profielcodes_ingevuld.met',
            # 'waternet/c/3 Profielpuntcodes_999.met',
            # 'waternet/c/4 Inpeilingen_tussen_waterlijnen.met',
            # 'waternet/d/1 Coordinaatvolgorde.met',
            # 'waternet/d/2 Dubbele_coordinaten.met',
            # 'waternet/d/4 Meetpunten_1_lijn.met',
            # 'waternet/e/1 Z1_groter_Z2.met',
            # 'waternet/e/2 Verschil_Z1_Z2.met',
            # 'waternet/W61-6 Bethunepolder_LG 2014 v2.met',
            )

        for filename in filenames:
            self.try_file(filename, True)
