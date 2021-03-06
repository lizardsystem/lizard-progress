# (c) Nelen & Schuurmans.  GPL licensed, see LICENSE.rst.
# -*- coding: utf-8 -*-

"""Tests for lizard_progress models.ReviewProject."""

from django.test import TestCase

from lizard_progress import models
from lizard_progress.tests.base import FixturesTestCase
from lizard_progress.tests.test_models import OrganizationF

from lxml import etree

import factory
import json
import os
import csv

# TODO: set these tests in test_models.py
# lizard_progress.tests.test_review_tool


class ReviewProjectF(factory.DjangoModelFactory):
    class Meta:
        model = models.ReviewProject

    name = 'Test reviewproject'
    slug = factory.Sequence(lambda n: 'testreviewproject%d' % n)
    organization = factory.SubFactory(OrganizationF)
    contractor = None
    reviews = None
    inspection_filler = None


class TestReviewProject(FixturesTestCase):
    """Tests for the ReviewProject model"""

    def setUp(self):
        self.test_files = os.path.join('lizard_progress',
                                       'tests',
                                       'test_met_files')
        self.name = 'Test reviewproject'
        self.ribx_file = 'lizard_progress/tests/test_met_files/ribx/Testbestand_Inlezen_beoordelingstool.ribx'
        self.single_pipe = 'lizard_progress/tests/test_met_files/ribx/single_pipe.ribx'
        self.single_manhole = 'lizard_progress/tests/test_met_files/ribx/single_manhole.ribx'

        self.organization = models.Organization.objects.create(
            name='Test organization'
        )
        self.rp = ReviewProjectF(
            name='Test reviewproject',
            organization=self.organization)

    def test_create_reviewProject(self):
        # Create blank ReviewProject
        pr = models.ReviewProject.objects.create(
            name='Test reviewproject',
            organization=self.organization)
        pr.save()

    def test_set_slug_and_save(self):
        organization = self.organization
        pr = self.rp
        pr.set_slug_and_save()
        self.assertTrue(pr.slug)
        self.assertTrue(unicode(pr.id) in pr.slug)
        self.assertTrue('test-reviewproject' in pr.slug)

    def test__parse_zb_a(self):
        tree = etree.parse(self.single_pipe)
        root = tree.getroot()
        element = root.find('ZB_A')
        pipe = self.rp._parse_zb_a(element)
        self.assertEqual('147715.18', pipe['Beginpunt x'])
        self.assertEqual('491929.01', pipe['Beginpunt y'])
        self.assertEqual('147779.16', pipe['Eindpunt x'])
        self.assertEqual('491974.99', pipe['Eindpunt y'])
        self.assertEquals(len(pipe['ZC']), 2)

    def test__parse_zb_c(self):
        tree = etree.parse(self.single_manhole)
        root = tree.getroot()
        element = root.find('ZB_C')
        manhole = self.rp._parse_zb_c(element)
        self.assertEqual('146916.82', manhole['x'])
        self.assertEqual('492326.42', manhole['y'])

    def test__parse_zc(self):
        tree = etree.parse(self.single_pipe)
        root = tree.getroot()
        zb_a = {
            'ABQ': '5',
            'Beginpunt x': '0',
            'Beginpunt y': '0',
            'Eindpunt x': '1',
            'Eindpunt y': '1'
        }
        element = root.find('ZB_A').find('ZC')
        inspection = self.rp._parse_zc(element, zb_a)
        self.assertTrue('Herstelmaatregel' in inspection.keys())
        self.assertTrue('Opmerking' in inspection.keys())

    def test_create_from_ribx(self):
        with self.settings(CELERY_ALWAYS_EAGER=True,
                           CELERY_EAGER_PROPAGATES_EXCEPTIONS=True):
            pr = models.ReviewProject.create_from_ribx(self.name,
                                                       self.ribx_file,
                                                       self.organization,
                                                       move=False)
        pr = models.ReviewProject.objects.get(pk=pr.pk)  # Refresh

        reviews = pr.reviews
        pipes = reviews['pipes']
        man_holes = reviews['manholes']

        self.assertEqual(len(pipes), 2)

        self.assertEqual('142739.23', pipes[0]['Beginpunt x'])
        self.assertEqual('486443.21', pipes[0]['Beginpunt y'])
        self.assertEqual('142776.84', pipes[0]['Eindpunt x'])
        self.assertEqual('486430.19', pipes[0]['Eindpunt y'])

    def test__manholes_to_points(self):
        with self.settings(CELERY_ALWAYS_EAGER=True,
                           CELERY_EAGER_PROPAGATES_EXCEPTIONS=True):
            pr = models.ReviewProject.create_from_ribx(self.name,
                                                       self.single_manhole,
                                                       self.organization,
                                                       move=False)
        pr = models.ReviewProject.objects.get(pk=pr.pk)  # Refresh

        geo_manholes = pr._manholes_to_points()
        self.assertTrue(geo_manholes.is_valid)

    def test__pipes_to_lines(self):
        with self.settings(CELERY_ALWAYS_EAGER=True,
                           CELERY_EAGER_PROPAGATES_EXCEPTIONS=True):
            pr = models.ReviewProject.create_from_ribx(self.name,
                                                       self.single_pipe,
                                                       self.organization,
                                                       move=False)
        pr = models.ReviewProject.objects.get(pk=pr.pk)  # Refresh

        geo_pipes = pr._pipes_to_lines()
        self.assertTrue(geo_pipes.is_valid)

    def test_generate_geojson_reviews(self):
        with self.settings(CELERY_ALWAYS_EAGER=True,
                           CELERY_EAGER_PROPAGATES_EXCEPTIONS=True):
            pr = models.ReviewProject.create_from_ribx(self.name,
                                                       self.ribx_file,
                                                       self.organization,
                                                       move=False)
        pr = models.ReviewProject.objects.get(pk=pr.pk)  # Refresh

        geojson = pr.generate_geojson_reviews()
        self.assertTrue(geojson.is_valid)

    def test_generate_feature_collection(self):
        with self.settings(CELERY_ALWAYS_EAGER=True,
                           CELERY_EAGER_PROPAGATES_EXCEPTIONS=True):
            pr = models.ReviewProject.create_from_ribx(self.name,
                                                       self.ribx_file,
                                                       self.organization,
                                                       move=False)
        pr = models.ReviewProject.objects.get(pk=pr.pk)  # Refresh

        pr.generate_feature_collection()
        geojson = json.loads(pr.feature_collection_geojson)
        self.assertEquals(len(geojson['features']), 2)

    def _calc_progress_manhole(self, manhole):
        progress = self.rp._calc_progress_manhole(manhole)
        self.assertEquals(progress, 0.0)

    def _calc_progress_pipe(self, pipe):
        progress = self.rp._calc_progress_pipe(pipe)
        self.assertEquals(progress, 100)

    def test_calc_progress(self):
        review_file = os.path.join(self.test_files,
                                   'review',
                                   'review_uncompleted.json')
        with open(review_file) as json_file:
            review = ReviewProjectF(reviews=json.load(json_file))
            uncompleted_manhole = review.reviews['manholes'][0]
            self._calc_progress_manhole(uncompleted_manhole)
            uncompleted_pipe = review.reviews['pipes'][0]
            self._calc_progress_pipe(uncompleted_pipe)
