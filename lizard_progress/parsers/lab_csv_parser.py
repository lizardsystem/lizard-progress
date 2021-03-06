from PIL.ImageFile import ImageFile
import csv
import logging

from lizard_progress import models

from lizard_progress.specifics import ProgressParser
from lizard_progress.specifics import UnSuccessfulParserResult

logger = logging.getLogger(__name__)


class LA(object):
    pass


class LabCsvParser(ProgressParser):
    ERRORS = {
        'not11': "Een regel moet 11 elementen bevatten.",
        }

    def parse(self, check_only=False):
        if isinstance(self.file_object, ImageFile):
            return UnSuccessfulParserResult()

        csvfile = csv.reader(self.file_object, delimiter=';')

        self.la = LA()
        self.la.line_number = 1  # Line number for in error messages
        firstrow = csvfile.next()

        if not firstrow or firstrow[0] != 'ogi_domgwcod':
            # Apparently not our type of file
            return UnSuccessfulParserResult()

        data = dict()

        for row in csvfile:
            self.la.line_number += 1
            if len(row) != 11:
                return self.error("not11")

            hydrovak_code = row[1]

            if not hydrovak_code in data:
                data[hydrovak_code] = dict()
            hydrovak_data = data[hydrovak_code]

            what = row[4]  # Wat is er gemeten
            unit = row[5]
            amount = row[6]
            date = row[7]
            time = row[8]

            hydrovak_data[what] = {
                'unit': unit,
                'amount': amount,
                'date': date,
                'time': time
                }

        if not check_only:
            measurements = []
            for hydrovak_code in data:
                # Get or create a location
                location, _ = models.Location.objects.get_or_create(
                    activity=self.activity,
                    location_code=hydrovak_code)

                # And a measurement to go along with it
                measurement, _ = models.Measurement.objects.get_or_create(
                    location=location)
                measurement.data = data[hydrovak_code]
                measurement.save()

                location.complete = True
                location.save()

                measurements.append(measurement)

            return self.success(measurements)
        else:
            return self.success([])
