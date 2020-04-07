"""
Compare earthquake magnitudes within or between their representations in earthquake catalogs.
"""

import datetime
import earthquake_location
import glob
from io import BytesIO
import math
import matplotlib.pyplot as plt
import numpy as np
from obspy.io.quakeml.core import Unpickler
import os
import pycurl
from scipy.stats import gmean
from scipy.odr import Model, Data, ODR
import time


quakeml_reader = Unpickler()


def ISC_event_query(minmagnitude, minlongitude, maxlongitude, minlatitude, maxlatitude, catalog_name,
                    comparison_magnitudes, starttime='0000-01-01T00:00:00Z', endtime='9999-01-01T00:00:00Z',
                    maxmagnitude=10):

    """
    Use obspy with pycurl to query event details from the ISC.
    Uses a file to save query results to to avoid crashing the computer due to memory filling.
    :param minmagnitude:
    :param minlongitude:
    :param maxlongitude:
    :param minlatitude:
    :param maxlatitude:
    :param starttime:
    :param endtime:
    :param maxmagnitude:
    :param catalog_name:
    :param comparison_magnitudes:
    :return:
    """

    # Curl ISC response and parse quakeml bytes string through obspy
    # using an interative query approach when a single query fails

    factor = 1
    success = False
    with open('catalog_data.txt', 'w') as outfile:
        pass
    while not success:

        successes = 0

        # Build time ranges for query
        starttime_dt = datetime.datetime.strptime(starttime, '%Y-%m-%dT%H:%M:%SZ')
        endtime_dt = datetime.datetime.strptime(endtime, '%Y-%m-%dT%H:%M:%SZ')
        time_ranges = [starttime_dt]
        for i in range(1, factor + 1):
            time_ranges.append(time_ranges[-1] +
                               datetime.timedelta(seconds=(endtime_dt - starttime_dt).total_seconds() / factor))

        # Run queries
        for i in range(1, len(time_ranges)):

            # Build query
            query = ""
            query = query.join(('http://www.isc.ac.uk/cgi-bin/web-db-v4?'
                                'out_format=CATQuakeML&request=COMPREHENSIVE&searchshape=RECT',
                                '&bot_lat=', str(minlatitude),
                                '&top_lat=', str(maxlatitude),
                                '&left_lon=', str(minlongitude),
                                '&right_lon=', str(maxlongitude),
                                '&min_mag=', str(minmagnitude),
                                '&start_year=', str(time_ranges[i - 1].year),
                                '&start_month=', str(time_ranges[i - 1].month),
                                '&start_day=', str(time_ranges[i - 1].day),
                                '&start_time=', str(time_ranges[i - 1].isoformat())[:19].split('T')[1][:-1],
                                '&end_year=', str(time_ranges[i].year),
                                '&end_month=', str(time_ranges[i].month),
                                '&end_day=', str(time_ranges[i].day),
                                '&end_time=', str(time_ranges[i].isoformat())[:19].split('T')[1][:-1],
                                '&max_mag=', str(maxmagnitude),
                                '&req_mag_type=Any'))

            try:

                print('\nAttempting ISC catalog query for events between ' + str(time_ranges[i - 1]) +
                      ' and ' + str(time_ranges[i]))

                queryresult = curl(query)
                if "Sorry, but your request cannot be processed at the present time." in queryresult.decode('ascii'):
                    # Wait a minute, then try again with the same query
                    print('Got \"Sorry, but your request cannot be processed at the present time.\" message. Waiting '
                          'one minute and trying again.')
                    time.sleep(60)
                    break

                catalog = quakeml_reader.loads(queryresult)
                events = catalog.events
                print('Query produced ' + str(len(events)) + ' events')
                successes += 1

            except:
                print('Failed! Query result is:')
                try:
                    print(queryresult)
                except:
                    print('No query result!')
                print('Will wait one minute before trying again.')
                time.sleep(60)
                if successes > 0:
                    print('Assuming query failed because no events exist in the time window')
                    successes += 1
                else:
                    factor += 100  # Only fails for huge datasets, so try minimise the size of the first new query
                    break

            # Save queryresult to file
            with open('catalog_data.txt', 'a') as outfile:
                outfile.write(queryresult.decode('utf-8'))

        if successes == len(time_ranges) - 1:
            success = True

    # Load all data from file
    print('Loading catalog data from file...')
    with open('catalog_data.txt', 'r') as infile:
        numentries = 0
        for row in infile:
            if '<?xml version="1.0" encoding="UTF-8"?>' in row and numentries == 0:
                # Catches the start of the first entry
                numentries += 1
                entry = ''
            elif '<?xml version="1.0" encoding="UTF-8"?>' in row and numentries > 0:
                # Catches when a new entry occurs
                if entry.encode('utf-8') == b'\n<quakeml xmlns="http://quakeml.org/xmlns/quakeml/1.2">No ' \
                                            b'events were found.\n':
                    # Catch when the current entry has no data
                    entry = ''
                else:
                    catalog = quakeml_reader.loads(entry.encode('utf-8'))
                    events = catalog.events
                    print('\nCurrent catalog has ' + str(len(events)) + ' events')

                    # Append new magnitude data to files
                    save_magnitude_timeseries(catalog, catalog_name, comparison_magnitudes)
                    entry = ''
            else:
                entry += row
        else:
            # Catch when the file ends
            if entry.encode('utf-8') != b'\n<quakeml xmlns="http://quakeml.org/xmlns/quakeml/1.2">No ' \
                                        b'events were found.\n':
                catalog = quakeml_reader.loads(entry.encode('utf-8'))
                events = catalog.events
                print('\nCurrent catalog has ' + str(len(events)) + ' events')

                # Append new magnitude data to files
                save_magnitude_timeseries(catalog, catalog_name, comparison_magnitudes)

    return events


def FDSN_event_query(service, minmagnitude, minlongitude, maxlongitude,
                     minlatitude, maxlatitude, catalog_name, comparison_magnitudes,
                     starttime='0000-01-01T00:00:00Z', endtime='9999-01-01T00:00:00Z', maxmagnitude=10):
  
    """
    Use obspy with pycurl to query event catalogs from FDSN members.
    Uses a file to save query results to to avoid crashing the computer due to memory filling.
    :param service:
    :param minmagnitude:
    :param maxmagnitude:
    :param minlongitude:
    :param maxlongitude:
    :param minlatitude:
    :param maxlatitude:
    :param starttime:
    :param endtime:
    :param catalog_name:
    :param comparison_magnitudes:
    :return:
    """

    # Adjust format if required
    if "usgs" in service:
        maxlongitude += 360

    # Curl FDSN response and parse quakeml bytes string through obspy
    # using an interative query approach when a single query fails

    factor = 1
    success = False
    with open('catalog_data.txt', 'w') as outfile:
        pass
    while not success:

        successes = 0

        # Build time ranges for query
        starttime_dt = datetime.datetime.strptime(starttime, '%Y-%m-%dT%H:%M:%SZ')
        endtime_dt = datetime.datetime.strptime(endtime, '%Y-%m-%dT%H:%M:%SZ')
        time_ranges = [starttime_dt]
        for i in range(1, factor + 1):
            time_ranges.append(time_ranges[-1] +
                               datetime.timedelta(seconds=(endtime_dt - starttime_dt).total_seconds() / factor))
        # Run queries
        for i in range(1, len(time_ranges)):

            # Build query
            query = ""
            query = query.join((service,
                                "query?",
                                "minmagnitude=",
                                str(minmagnitude),
                                "&maxmagnitude=",
                                str(maxmagnitude),
                                "&minlatitude=",
                                str(minlatitude),
                                "&maxlatitude=",
                                str(maxlatitude),
                                "&minlongitude=",
                                str(minlongitude),
                                "&maxlongitude=",
                                str(maxlongitude),
                                "&starttime=",
                                time_ranges[i - 1].isoformat(),
                                "&endtime=",
                                time_ranges[i].isoformat()))

            try:

                print('\nAttempting FDSN catalog query for events between ' + str(time_ranges[i - 1]) +
                      ' and ' + str(time_ranges[i]))

                queryresult = curl(query)

                catalog = quakeml_reader.loads(queryresult)
                events = catalog.events
                print('Query produced ' + str(len(events)) + ' events')
                successes += 1

            except:
                print('Failed! Query result is:')
                try:
                    print(queryresult)
                except:
                    print('No query result!')
                if successes > 0:
                    print('Assuming query failed because no events exist at high magnitude range')
                    successes += 1
                else:
                    factor += 100  # Only fails for huge datasets, so try minimise the size of the first new query
                    break

            # Save queryresult to file
            with open('catalog_data.txt', 'a') as outfile:
                outfile.write(queryresult.decode('utf-8'))

        if successes == len(time_ranges) - 1:
            success = True

    # Load all data from file
    print('Loading catalog data from file...')
    with open('catalog_data.txt', 'r') as infile:
        numentries = 0
        rc = -1
        for row in infile:
            rc += 1
            row = row.strip()  # Remove leading and trailing whitespaces
            if '<?xml version="1.0" encoding="UTF-8"?>' in row and numentries == 0:
                # Catches the start of the first entry
                numentries += 1
                entry = ''
            elif '<?xml version="1.0" encoding="UTF-8"?>' in row and numentries > 0:
                if row[-len('<?xml version="1.0" encoding="UTF-8"?>'):] == '<?xml version="1.0" encoding="UTF-8"?>' and \
                        row != '<?xml version="1.0" encoding="UTF-8"?>':
                    # If the XML declaration is at the end of a row containing other data
                    row = row[:-len('<?xml version="1.0" encoding="UTF-8"?>')]
                # Catches when a new entry occurs
                if entry.encode('utf-8') == b'\n<quakeml xmlns="http://quakeml.org/xmlns/quakeml/1.2">No ' \
                                            b'events were found.\n':
                    # Catch when the current entry has no data
                    entry = ''
                else:
                    entry += row
                    catalog = quakeml_reader.loads(entry.encode('utf-8'))
                    # Remove unnecessary elements in the catalog to reduce RAM use of the code
                    for m in range(len(catalog)):
                        catalog[m].amplitudes = None
                        catalog[m].station_magnitudes = None
                    events = catalog.events
                    print('Current catalog has ' + str(len(events)) + ' events')

                    # Append new magnitude data to files
                    save_magnitude_timeseries(catalog, catalog_name, comparison_magnitudes)
                    entry = ''
            else:
                entry += row
        else:
            # Catch when the file ends
            if entry.encode('utf-8') != b'\n<quakeml xmlns="http://quakeml.org/xmlns/quakeml/1.2">No ' \
                                        b'events were found.\n':
                catalog = quakeml_reader.loads(entry.encode('utf-8'))
                events = catalog.events
                print('Current catalog has ' + str(len(events)) + ' events')

                # Append new magnitude data to files
                save_magnitude_timeseries(catalog, catalog_name, comparison_magnitudes)

    return events


def curl(curlstr):

    """
    Perform curl with curlstr
    :param curlstr: string to curl
    :return: curl output
    """

    buffer = BytesIO()
    c = pycurl.Curl()
    c.setopt(c.URL, curlstr)
    c.setopt(c.WRITEDATA, buffer)
    c.perform()
    c.close()

    return buffer.getvalue()


def to_cartesian(latitude, longitude, depth):

    """
    Convert a point on the Earth in spherical coordinates to cartesian coordinates
    :param latitude: point latitude in decimal degrees, south is negative
    :param longitude: point longitude in decimal degrees, west is negative
    :param depth: point depth in metres, down is positive
    :return: cartesian coordinates of the point
    """

    # Ensure variables are floats
    latitude = float(latitude)
    longitude = float(longitude)
    depth = float(depth)

    Re = 6371000  # average Earth radius in m (assuming a spherical Earth)

    # Convert to spherical coordinate conventions
    r = Re - depth
    if longitude < 0:
        longitude += 180

    # Convert to cartesian coordinates
    x = r * math.sin(latitude) * math.cos(longitude)
    y = r * math.sin(latitude) * math.sin(longitude)
    z = r * math.cos(latitude)

    return x, y, z


def save_magnitude_timeseries(catalog, catalog_name, comparison_magnitudes):

    """
    Saves magnitude timeseries to disk for each magnitude type in the comparison_magnitudes
    list corresponding to a given catalog
    :param catalog: list containing obspy event objects
    :param catalog_name: name of catalog (for file naming)
    :param comparison_magnitudes: list containing all magnitudes in the given catalog to extract
    :return: saves matched events with matched magnitudes to a csv file
    """

    print('\nBuilding magnitude timeseries...')
    datalist = [[[] for i in range(len(comparison_magnitudes))] for k in range(8)]
    for i in range(len(comparison_magnitudes)):
        for event in catalog:
            for magnitude in event.magnitudes:
                if magnitude.magnitude_type == comparison_magnitudes[i]:
                    datalist[0][i].append(event.resource_id)
                    datalist[1][i].append(event.origins[0].time)
                    datalist[2][i].append(magnitude.magnitude_type)
                    datalist[3][i].append(magnitude.mag)
                    datalist[4][i].append(event.origins[0].latitude)
                    datalist[5][i].append(event.origins[0].longitude)
                    datalist[6][i].append(event.origins[0].depth)
                    try:
                        datalist[7][j].append(event.event_descriptions[0].text)
                    except:
                        datalist[7][j].append('')

        if len(datalist[0][i]) == 0:
            print('No magnitudes of type ' + comparison_magnitudes[i] + ' were found in the catalog.')
            continue
        else:
            print('Saving data to file for catalog ' + catalog_name + ' for magnitude type ' +
                  comparison_magnitudes[i] + '...')

            with open(catalog_name + '_' + comparison_magnitudes[i] + '_timeseries.csv', 'a') as outfile:
                for n in range(len(datalist[0][i])):
                    outfile.write(
                        str(datalist[0][i][n]) + ',' + str(datalist[1][i][n]) + ',' + datalist[2][i][n]
                        + ',' + str(datalist[3][i][n]) + ',' + str(datalist[4][i][n]) + ',' + str(datalist[5][i][n])
                        + ',' + str(datalist[6][i][n]) + '\n')


def GeoNet_Mw(minmagnitude, starttime, endtime):

    """
    Query GeoNet Mw catalog from GitHub
    :param minmagnitude:
    :param starttime:
    :param endtime:
    :return: saves to file datalist in the same format as generate_timeseries function
    """

    print('\nBuilding GeoNet Mw timeseries')
    URL = "https://raw.githubusercontent.com/GeoNet/data/master/moment-tensor/GeoNet_CMT_solutions.csv"
    result = curl(URL).decode('ascii')
    print("")

    datalist = [[] for i in range(7)]
    rc = 0
    for row in result.split('\n'):
        if rc == 0:
            rc += 1
            continue
        else:
            rowsplit = row.split(',')
            if len(rowsplit) < 2:
                continue
            else:
                time = rowsplit[1]
                
                if ((datetime.datetime.strptime(time, '%Y%m%d%H%M%S') >= datetime.datetime.strptime(starttime,
                                                                                                    '%Y-%m-%dT%H:%M:%SZ'))
                        and (float(rowsplit[11]) >= minmagnitude)):
    
                    try:
                        URL = "https://service.geonet.org.nz/fdsnws/event/1/query?eventid=" + rowsplit[0]
                        event = quakeml_reader.loads(curl(URL))[0]
                    except:
                        print('Event with eventID ' + rowsplit[0] + ' not in GeoNet catalog?')

                    datalist[0].append('smi:nz.org.geonet/' + rowsplit[0])
                    datalist[2].append('Mw')
                    datalist[3].append(rowsplit[11])

                    # Get timing and location details from equivalent GeoNet catalog event
                    datalist[1].append(event.origins[0].time)
                    datalist[4].append(event.origins[0].latitude)
                    datalist[5].append(event.origins[0].longitude)
                    datalist[6].append(event.origins[0].depth)

    if len(datalist[0]) == 0:
        return
    else:
        with open('GeoNet_catalog_Mw_timeseries.csv', 'w') as outfile:
            outfile.write('eventID,origin_time,magnitude_type,magnitude,latitude,longitude,depth\n')
        with open('GeoNet_catalog_Mw_timeseries.csv', 'a') as outfile:
            for n in range(len(datalist[0])):
                outfile.write(
                    str(datalist[0][n]) + ',' + str(datalist[1][n]) + ',' + datalist[2][n]
                    + ',' + str(datalist[3][n]) + ',' + str(datalist[4][n]) + ',' + str(datalist[5][n])
                    + ',' + str(datalist[6][n]) + '\n')


def parse_data(filelist, split_str, starttime, endtime):

    """
    Parse magnitude timeseries or matches from csv file, using start and end times for time filtering
    :param filelist: list of files
    :param split_str: string to split filename by to get file type
    :param starttime: do not load data from before this time
    :param endtime: do not load data from after this time
    :return: list of data in file, list of type of data in files
    """

    data_types = []
    datalist = [[[] for j in range(len(filelist))] for i in range(7)]
    for j in range(len(filelist)):
        file = filelist[j]
        with open(file, 'r') as infile:
            rc = 0
            for row in infile:
                if rc == 0:
                    rc += 1
                else:
                    rowsplit = row.split(',')
                    if (starttime <=
                        datetime.datetime.strptime(rowsplit[1], '%Y-%m-%dT%H:%M:%S.%fZ') <=
                        endtime):
                        for i in range(len(rowsplit)):
                            datalist[i][j].append(str(rowsplit[i]))
        if len(datalist[0][j]) > 0:
            data_types.append(file.split('/')[-1].split(split_str)[0])

    return datalist, data_types


def match_magnitudes(magnitude_timeseries, timeseries_types, catalog_names, comparison_magnitudes, max_dt, max_dist,
                     rms_threshold, show_matching):

    """
    Match events between two catalogs and save all events and their matched magnitudes to file
    :param magnitude_timeseries:
    :param timeseries_types:
    :param catalog_names:
    :param comparison_magnitudes: list of two lists containing all magnitudes to match
                                between the catalog and the reference catalog
    :param max_dt: maximum seconds (absolute) between events for them to be matched
    :param max_dist: maximum distance (absolute) between events for them to be matched
    :param rms_threshold: origin time difference at which events from different catalogs are considered to
           represent the same earthquake
    :param show_matching: whether to plot relative distance and time of all events that have matched
    :return: saves matched events with matched magnitudes to a csv file
    """

    # Build column types for output csv (columns)
    columns = ['eventID', 'matchID', 'RMS_error', 'latitude', 'longitude', 'depth']
    magnitudes_columns = []
    for magnitude_type in timeseries_types:
        magnitudes_columns.append(magnitude_type.split('_')[-1])
    magnitudes_columns = list(set(magnitudes_columns))
    magnitudes_columns.sort()
    columns.extend(magnitudes_columns)

    # Generate list of events for output csv (rows)
    event_list = []
    for n in range(len(magnitude_timeseries[0])):
        for m in range(len(magnitude_timeseries[0][n])):
            # Only populate the event list with the non-reference catalog
            if timeseries_types[n].split('_')[0] in catalog_names[0]:
                event_list.append(magnitude_timeseries[0][n][m])
    event_list = list(set(event_list))

    # Pre-populated eventID, location, and RMS error in datalist prior to matching
    datalist = [[[] for m in range(len(event_list))] for n in range(len(columns))]
    for n in range(len(magnitude_timeseries[0])):
        for k in range(len(magnitude_timeseries[0][n])):
            try:
                event_index = event_list.index(magnitude_timeseries[0][n][k])
                datalist[0][event_index] = magnitude_timeseries[0][n][k]
                datalist[2][event_index] = None  # Begin with no match
                datalist[2][event_index] = '0'  # Length 0 for internal matches: external matches will overwrite
                datalist[3][event_index] = magnitude_timeseries[4][n][k]
                datalist[4][event_index] = magnitude_timeseries[5][n][k]
                datalist[5][event_index] = str(float(magnitude_timeseries[6][n][k]))  # Remove trailing newline
            except: # Fails when the event is not from the non-reference catalog
                pass

    # Match events between timeseries and fill in magnitude information in the datalist
    complete_pairs = []
    matched_temporal_lengths = []
    matched_spatial_lengths = []
    for n in range(len(timeseries_types)):
        for m in range(len(timeseries_types)):
            if str(m) + ',' + str(n) in complete_pairs:
                # Don't repeat matching
                continue
            if timeseries_types[m].split('_')[0] == timeseries_types[n].split('_')[0] and \
                    timeseries_types[m].split('_')[2] == timeseries_types[n].split('_')[2]:
                # Don't match the same data against itself
                continue

            print('Looking for matching events with magnitude types ' + timeseries_types[n] +
                  ' and ' + timeseries_types[m] + '...')
            if timeseries_types[m].split('_')[0] == catalog_names[0].split('_')[0] and \
                    (timeseries_types[m].split('_')[2] in comparison_magnitudes[0] or
                     catalog_names[0] == catalog_names[1]):
                # We have another of our first sets of comparison magnitudes:
                # This will do the internal matching routine.
                # Find matches and load data into datalist
                # Go through all the entires for the nth magnitude type
                for k in range(len(magnitude_timeseries[0][n])):
                    event_index = event_list.index(magnitude_timeseries[0][n][k])
                    # Go through all the entires for the mth magnitude type
                    for l in range(len(magnitude_timeseries[0][m])):
                        # Match based on eventID
                        if magnitude_timeseries[0][n][k] == magnitude_timeseries[0][m][l]:
                            datalist[columns.index(timeseries_types[n].split('_')[2])][event_index] = \
                                magnitude_timeseries[3][n][k]
                            datalist[columns.index(timeseries_types[m].split('_')[2])][event_index] = \
                                magnitude_timeseries[3][m][l]
            elif timeseries_types[m].split('_')[0] == catalog_names[1].split('_')[0] and \
                    timeseries_types[m].split('_')[2] in comparison_magnitudes[1]:
                # We have one of our second sets of comparison magnitudes:
                # This will do the external matching routine.
                for k in range(len(magnitude_timeseries[0][n])):
                    event_index = event_list.index(magnitude_timeseries[0][n][k])
                    # Check to see if the event has already been matched
                    if datalist[1][event_index]:
                        # If it has, skip the matching routine and save the new data
                        try:
                            match_idx = magnitude_timeseries[0][m].index(datalist[1][event_index])
                            print('Match exists already for event ' + str(magnitude_timeseries[0][n][k]) +
                                  '. This event has been matched with event at index ' + str(match_idx))
                            datalist[columns.index(timeseries_types[n].split('_')[2])][event_index] = \
                                magnitude_timeseries[3][n][k]
                            datalist[columns.index(timeseries_types[m].split('_')[2])][event_index] = \
                                magnitude_timeseries[3][m][match_idx]
                            continue
                        except ValueError:
                            # This will occur if a match exists, but that event does not have the magnitude of
                            # the current type. The code will produce magnitudes from two different events within
                            # the same RMS error threshold! Or perhaps only for the former if the latter does not
                            # fall within the threshold.
                            pass

                    # Calculate 2D length between event and reference events for matching criteria

                    temporal_lengths = []
                    spatial_lengths = []
                    lengths = []
                    indices = []
                    if magnitude_timeseries[6][n][k][:4] == 'None':  # Ignore events with no depth
                        continue
                    ETi, ELa, ELo, EDe = [datetime.datetime.strptime(magnitude_timeseries[1][n][k],
                                                                     '%Y-%m-%dT%H:%M:%S.%fZ'),
                                          float(magnitude_timeseries[4][n][k]),
                                          float(magnitude_timeseries[5][n][k]),
                                          float(magnitude_timeseries[6][n][k])]
                    Ex, Ey, Ez = to_cartesian(ELa, ELo, EDe)

                    for l in range(len(magnitude_timeseries[0][m])):
                        if magnitude_timeseries[6][m][l][:4] == 'None':  # Ignore events with no depth
                            continue
                        RETi, RELa, RELo, REDe = [datetime.datetime.strptime(magnitude_timeseries[1][m][l],
                                                                             '%Y-%m-%dT%H:%M:%S.%fZ'),
                                                  float(magnitude_timeseries[4][m][l]),
                                                  float(magnitude_timeseries[5][m][l]),
                                                  float(magnitude_timeseries[6][m][l])]
                        REx, REy, REz = to_cartesian(RELa, RELo, REDe)

                        temporal_length = abs((ETi - RETi).total_seconds())
                        if temporal_length > max_dt:
                            continue
                        else:
                            temporal_lengths.append(temporal_length)

                        spatial_length = math.sqrt((Ex - REx) ** 2 + (Ey - REy) ** 2 + (Ez - REz) ** 2) / 1000.0
                        if spatial_length > max_dist:
                            continue
                        else:
                            spatial_lengths.append(spatial_length)

                        lengths.append(math.sqrt(temporal_length ** 2 + spatial_length ** 2))
                        indices.append(l)

                    if len(lengths) > 0:

                        # Search all possible matches and use an earthquake location routine to test
                        # if the events are representing the same earthquake. The rms threshold value
                        # is used as a proxy for this.

                        # Sort the length lists
                        lengths, spatial_lengths, temporal_lengths, indices, = zip(*sorted(zip(lengths,
                                                                                               spatial_lengths,
                                                                                               temporal_lengths,
                                                                                               indices)))

                        # Make the event file to use in the earthquake location
                        event_file = open('temporary_event_file', 'w')
                        event_file.write('eventID\n' + str(magnitude_timeseries[0][n][k].split('/')[-1]) + '\n')
                        event_file.close()

                        # Begin the search with the event match with smallest length and end when a match is found
                        # that meets the rms threshold.
                        # NOTE: only works for reference catalog being the GeoNet catalog currently!
                        # event_file contains the eventID from the GeoNet catalog
                        # test_origins contains the potential match hypocentre and origin time
                        for l in range(len(indices)):
                            match_idx = indices[l]

                            test_origins = open('temporary_test_origins', 'w')
                            test_origins.write('latitude,longitude,depth,origin_time\n' +
                                               str(magnitude_timeseries[4][m][match_idx]) + ',' +
                                               str(magnitude_timeseries[5][m][match_idx]) + ',' +
                                               str(magnitude_timeseries[6][m][match_idx][:-1]) + ',' +
                                               str(datetime.datetime.strptime(magnitude_timeseries[1][m][match_idx],
                                                                              '%Y-%m-%dT%H:%M:%S.%fZ').isoformat()) +
                                               'Z\n')
                            test_origins.close()

                            # Convert and collate data into format expected by earthquake location code
                            arrival_time_data, arrival_time_data_header, grid_points, grid_header, test_origins = \
                                earthquake_location.parse_files(eventid_file='temporary_event_file',
                                                                test_origins='temporary_test_origins',
                                                                mode='spherical')

                            # Check arrival time data is non-empty, and if it is, ensure arrival is ignored
                            if len(arrival_time_data) == 1 and len(arrival_time_data[0]) == 0:
                                print('No arrival time data exists for this event! It will produce no match.')
                                earthquake_origins, rms_errors = [[0, 0, 0, datetime.datetime.now()], [9999]]
                            else:  # Otherwise, perform earthquake location
                                earthquake_origins, rms_errors = earthquake_location.test_test_origins('grid_search',
                                                                                                       arrival_time_data,
                                                                                                       arrival_time_data_header,
                                                                                                       grid_points,
                                                                                                       grid_header,
                                                                                                       test_origins)
                            rms_error = rms_errors[0]
                            print('For match_idx ' + str(match_idx) + ' rms error is ' + str(rms_error))

                            if rms_error <= rms_threshold:
                                print('Matched event ' + str(magnitude_timeseries[0][n][k]) +
                                      ' with event at index ' + str(match_idx))
                                # Save the data for the match
                                datalist[1][event_index] = magnitude_timeseries[0][m][match_idx]
                                datalist[2][event_index] = str(rms_error)
                                datalist[columns.index(timeseries_types[n].split('_')[2])][event_index] = \
                                    magnitude_timeseries[3][n][k]
                                datalist[columns.index(timeseries_types[m].split('_')[2])][event_index] = \
                                    magnitude_timeseries[3][m][match_idx]
                                matched_spatial_lengths.append(spatial_lengths[indices.index(match_idx)])
                                matched_temporal_lengths.append(temporal_lengths[indices.index(match_idx)])
                                break  # break on the first matching event

                        os.remove('temporary_event_file')
                        os.remove('temporary_test_origins')

            complete_pairs.append(str(n) + ',' + str(m))

    if show_matching:

        print('\nNOTE: To investigate the spread of matched data in an unconstrained format, ensure maximum limits are'
              '>=1E9\n')

        plt.scatter(matched_temporal_lengths, matched_spatial_lengths, s=2)
        plt.xlabel('relative time (s)', labelpad=15)
        plt.ylabel('relative distance (km)', labelpad=15)
        plt.title('relative distance vs. time for all matched events')
        plt.tight_layout()
        plt.show()

    # Write datalist to file
    with open('magnitude_matches_all.csv', 'w') as outfile:
        header = ""
        for column in columns:
            header += column + ','
        header = header[:-1]
        outfile.write(header + '\n')
    with open('magnitude_matches_all.csv', 'a') as outfile:
        for m in range(len(datalist[0])):
            outstr = ""
            for n in range(len(datalist)):
                try:
                    outstr += datalist[n][m] + ','
                except:
                    outstr += "nan,"
            outfile.write(outstr[:-1] + '\n')


def cumulative_sum(times):

    """
    Generate a cumulative sum timeseries for event times in times
    :param times: list of ISO8601 format times (strings)
    :return: list of event times (datetime objects), cumulative sum at each event time (list of int)
    """

    cumulative_event_sum = 0
    cumulative_event_sums = []
    event_times = []

    # Generate cumulative sum list and list of event times

    times.sort()
    for time in times:

        cumulative_event_sum += 1
        cumulative_event_sums.append(cumulative_event_sum)

        event_time = datetime.datetime.strptime(time, '%Y-%m-%dT%H:%M:%S.%fZ')
        event_times.append(event_time)

    return event_times, cumulative_event_sums


def f(P, x):

    """
    Point on line function to use in orthogonal regression
    :param P: m, c values for line
    :param x: dataset values
    :return point on line values for x value in x
    """

    return P[0] * x + P[1]


def orthregress(x, y):

    """
    Perform an orthogonal distance regression,
    :param x: dataset 1 values
    :param y: dataset 2 values
    :return: gradient, intercept of orthogonal distance regression
    """

    # Run orthogonal regression

    model = Model(f)
    data = Data(x, y)
    odr = ODR(data, model, beta0=[1, 1])
    output = odr.run()
    m, c = output.beta

    return m, c


# Set data gathering parameters

minmagnitude = 3  # minimum event magnitude to get from catalog
minlatitude, maxlatitude = -90, 90  # minimum and maximum latitude for event search window
minlongitude, maxlongitude = 0, -0.001  # western and eastern longitude for event search window
starttime = '2012-01-01T00:00:00Z'  # event query starttime
endtime = '2021-01-01T00:00:00Z' #'2020-03-01T00:00:00'  # event query endtime, 'now' will set it to the current time

if endtime == 'now':
    endtime = str(datetime.datetime.now().isoformat())[:19]

# Define catalogs and their associated FDSN webservice event URL. If a catalog is 'ISC_catalog' then the ISC catalog
# query will be used instead of the FDSN catalog query.

catalog_names = ['GeoNet_catalog', 'USGS_catalog']
# catalog_names = ['GeoNet_catalog']
# services = ["https://service.geonet.org.nz/fdsnws/event/1/"]
services = ["https://service.geonet.org.nz/fdsnws/event/1/", "https://earthquake.usgs.gov/fdsnws/event/1/"] # "https://service.geonet.org.nz/fdsnws/event/1/"]

# catalog_names = ['ISC_catalog', 'ISC_catalog']
# services = [None, None]  # If 'ISC_catalog' is given as an entry above, the corresponding services entry can be anything
catalogs = [[] for i in range(len(catalog_names))]

# Define comparison magnitudes: first nested list is from GeoNet catalog, second if from USGS
# Code will combine all magnitudes across the two catalogs in the final magnitude database,
# UNLESS catalogs are the same.
# NOTE: magnitudes are case-sensitive! Make sure you get the case right!
# If you want to compare magnitudes across a single catalog,
# you will need to repeat its details as both the comparison and reference catalogs.

comparison_magnitudes = [['M', 'ML', 'MLv', 'mB', 'Mw(mB)', 'Mw'], ['mww']] #['M', 'ML', 'MLv', 'mB', 'Mw(mB)', 'Mw']]
# comparison_magnitudes = [['M', 'ML', 'MLv', 'mB', 'Mw(mB)', 'Mw']]
# comparison_magnitudes = [['mB', 'mb'], ['MW']]

# Set matching parameters

max_dt = 100  # maximum time (s) between events in separate catalogs for them to be considered records of
              # the same earthquake
max_dist = 1000  # maximum distance (km) "
rms_threshold = 5  # origin time potential matches must be within (in seconds) when one is relocated using the
                    # arrival time picks of the other in a spherical Earth grid search.

# Set what level of processing you want the script to do
build_magnitude_timeseries = True
build_GeoNet_Mw_timeseries = True
gb_plotting = True
matching = True
show_matching = False

# Build event catalogs from FDSN
if build_magnitude_timeseries:

    # Prepare files for outputs
    for i in range(len(catalog_names)):
        for j in range(len(comparison_magnitudes[i])):
            with open(catalog_names[i] + '_' + comparison_magnitudes[i][j] + '_timeseries.csv', 'w') as outfile:
                outfile.write('eventID,origin_time,magnitude_type,magnitude,latitude,longitude,depth,description\n')

    print('\nSearching earthquake catalogs for events above magnitude ' + str(minmagnitude) +
          ' between ' + str(minlatitude) + ' and ' + str(maxlatitude) + ' degrees latitude and ' +
          str(minlongitude) + ' and ' + str(maxlongitude) + ' degrees longitude after ' + str(starttime)+
          ' and before ' + str(endtime))

    ISC_catalog_idx = None
    for n in range(len(catalogs)):

        if catalog_names[n] == 'ISC_catalog':
            if ISC_catalog_idx is None:
                catalogs[n] = ISC_event_query(minmagnitude, minlongitude, maxlongitude, minlatitude, maxlatitude,
                                              catalog_names[n], comparison_magnitudes[n], starttime, endtime)
                ISC_catalog_idx = n
            else:
                catalogs[n] = catalogs[ISC_catalog_idx]
        else:
            catalogs[n] = FDSN_event_query(services[n], minmagnitude, minlongitude, maxlongitude,
                                           minlatitude, maxlatitude, catalog_names[n],
                                           comparison_magnitudes[n], starttime, endtime)

# Build GeoNet Mw catalog

if build_GeoNet_Mw_timeseries:

    GeoNet_Mw(minmagnitude, starttime, endtime)

# Convert date strings to datetime objects

starttime = datetime.datetime.strptime(starttime, '%Y-%m-%dT%H:%M:%SZ')
endtime = datetime.datetime.strptime(endtime, '%Y-%m-%dT%H:%M:%SZ')

if matching or gb_plotting:

    # Parse all data

    magnitude_timeseries_files = glob.glob('./*timeseries.csv')
    magnitude_timeseries, timeseries_types = parse_data(magnitude_timeseries_files, '_timeseries',
                                                        starttime, endtime)

if gb_plotting:

    # Build plotting dataset
    plt.figure()

    for m in range(len(magnitude_timeseries[0])):

        xdec = []
        for n in range(len(magnitude_timeseries[0][m])):
            xdec.append(round(float(magnitude_timeseries[3][m][n]), 1))
        x = list(set(xdec))
        y = [0] * len(x)
        for xval in x:
            y[x.index(xval)] = xdec.count(xval)

        # Plot the data
        plt.scatter(x, y, s=1)

        # Add plot features for clarity

        plt.xlabel('magnitude value')
        plt.ylabel(timeseries_types[m])
        plt.grid(which='major', axis='both', linestyle='-', alpha=0.5)
        plt.savefig(timeseries_types[m] + '_gutenberg_richter_rel.png', format='png', dpi=300)
        plt.close()

if matching:

    # Do matching

    print("Matching events within temporal and spatial distance limits and with the desired magnitude types")

    match_magnitudes(magnitude_timeseries, timeseries_types, catalog_names, comparison_magnitudes, max_dt, max_dist,
                     rms_threshold, show_matching)

# Load magnitude match data

with open('./magnitude_matches_all.csv', 'r') as openfile:
    rc = 0
    for row in openfile:
        if rc == 0:
            data_types = row.split(',')
            data_types[-1] = data_types[-1][:-1]
            datalist = [[] for i in range(len(data_types))]
            rc += 1
        else:
            rowsplit = row.split(',')
            for i in range(len(rowsplit)):
                datalist[i].append(rowsplit[i])

print('Saving plots...')

# Magnitude value plotting

complete_pairs = []
for n in range(5, len(data_types)):
    # Ensure reference magnitudes are only ever on the y-axis
    if data_types[n] not in comparison_magnitudes[0]:
        continue
    for m in range(5, len(data_types)):
        # Ensure comparison magnitudes are only ever on the x-axis
        if data_types[m] not in comparison_magnitudes[1]:
            continue

        # Don't repeat plotting
        if n == m or str(m) + ',' + str(n) in complete_pairs:
            continue

        # Build plotting dataset
        plt.figure()
        x, xdec = [], []
        y = []
        for k in range(len(datalist[0])):
            if datalist[n][k][:3] != 'nan' and datalist[m][k][:3] != 'nan':
                x.append(float(datalist[m][k]))
                xdec.append(round(float(datalist[m][k]), 1))
                y.append(float(datalist[n][k]))

        # Plot the data
        plt.scatter(x, y, s=1)

        # Bin the y data to the corresponding x data and plot the mean value in each bin with size propotional
        # to number of data in the bin.
        x_vals = list(set(xdec))
        binned_yvals = [[] for l in range(len(x_vals))]
        for l in range(len(xdec)):
            x_idx = x_vals.index(xdec[l])
            binned_yvals[x_idx].append(y[l])
        mean_yvals = [0] * len(binned_yvals)
        n_yvals = [0] * len(binned_yvals)
        for l in range(len(binned_yvals)):
            mean_yvals[l] = gmean(binned_yvals[l])
            n_yvals[l] = len(binned_yvals[l])
        n_tot = sum(n_yvals)
        plt.scatter(x_vals, mean_yvals, s=n_yvals, edgecolors='k', linewidths=1)

        # Plot a line showing the 1:1 magnitude relationship for reference

        plt.plot(range(11), range(11), color='k', linestyle='--', linewidth=0.5, alpha=0.5)

        # Do an orthogonal distance regression and plot this overtop of the data, showing the
        # linear relationship between the magnitudes

        slope, intercept = orthregress(x, y)
        plt.plot([0, 10], [intercept, slope * 10 + intercept], color='k', linewidth=0.5, alpha=0.5)

        # Add plot features for clarity

        plt.xlabel(data_types[m])
        plt.ylabel(data_types[n])
        plt.grid(which='major', axis='both', linestyle='-', alpha=0.5)
        plt.xlim(2, 10)
        plt.ylim(2, 10)
        plt.title('m=' + str(slope)[:5] + ', c=' + str(intercept)[:5] + ', N=' + str(n_tot), y=1.03)
        plt.gca().set_aspect('equal', adjustable='box')
        plt.savefig(data_types[n] + '_' + data_types[m] + '.png', format='png', dpi=300)
        plt.close()

        complete_pairs.append(str(n) + ',' + str(m))

        # Use machine learning to fit a polynomial function to the data

        import pandas as pd
        from sklearn.linear_model import LassoCV
        from sklearn.model_selection import train_test_split

        def lasso_regression(data, predictors, alpha, models_to_plot={}):

            # Test/train split
            X_train, X_test, y_train, y_test = train_test_split(data['x'], data['y'], test_size=0.3)
            X_train, y_train = zip(*sorted(zip(X_train, y_train)))  # Order x and y
            X_test, y_test = zip(*sorted(zip(X_test, y_test)))  # Order x and y

            train_data = pd.DataFrame(np.column_stack([X_train, y_train]), columns=['x', 'y'])
            test_data = pd.DataFrame(np.column_stack([X_test, y_test]), columns=['x', 'y'])
            for i in range(2, 16):  # power of 1 is already there
                colname = 'x_%d' % i  # new var will be x_power
                train_data[colname] = train_data['x'] ** i
                test_data[colname] = test_data['x'] ** i

            # Fit the model
            lassoreg = LassoCV(eps=0.0001, alphas=[alpha], max_iter=1e5, normalize=True, cv=5)
            lassoreg.fit(train_data[predictors], train_data['y'])
            y_pred = lassoreg.predict(test_data[predictors])

            # Return the result in pre-defined format
            rss = np.sqrt(sum((y_pred - test_data['y']) ** 2))
            ret = [rss]
            ret.extend([lassoreg.intercept_])
            ret.extend(lassoreg.coef_)

            # Check if a plot is to be made for the entered alpha
            if alpha in models_to_plot:
                plt.subplot(models_to_plot[alpha])
                plt.tight_layout()
                plt.scatter(data['x'], data['y'], color='red', s=0.1)
                plt.scatter(x_vals, mean_yvals, s=n_yvals, edgecolors='k', linewidths=1)
                plt.plot(test_data['x'], y_pred, color='b', linewidth=1)
                plt.title('Plot for alpha: %.3g' % alpha + '\n' + 'RSS: %.3g' % rss)

            return ret


        # Define data as a dataframe
        data = pd.DataFrame(np.column_stack([x, y]), columns=['x', 'y'])
        # data = pd.DataFrame(np.column_stack([x_vals, mean_yvals]), columns=['x', 'y'])

        # Initialize predictors to all 15 powers of x
        predictors = ['x']
        predictors.extend(['x_%d' % i for i in range(2, 16)])

        # Define the alpha values to test
        alpha_lasso = [1e-4, 5e-4, 1e-3, 2e-3, 3e-3, 4e-3]

        # Initialize the dataframe to store coefficients
        col = ['rss', 'intercept'] + ['coef_x_%d' % i for i in range(1, 16)]
        ind = ['alpha_%.2g' % alpha_lasso[i] for i in range(len(alpha_lasso))]
        coef_matrix_lasso = pd.DataFrame(index=ind, columns=col)

        # Define the alpha value models to plot
        models_to_plot = {1e-4: 231, 5e-4: 232, 1e-3: 233, 2e-3: 234, 3e-3: 235, 4e-3: 236}

        # Iterate over the alpha values:
        for i in range(len(alpha_lasso)):
            coef_matrix_lasso.iloc[i,] = lasso_regression(data, predictors, alpha_lasso[i], models_to_plot)
        plt.show()
