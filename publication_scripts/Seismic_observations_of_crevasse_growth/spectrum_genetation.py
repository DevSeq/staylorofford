#!/usr/bin/env python3
# -*- coding: utf-8 
"""
Frequency domain detection using multiple python instances.
"""

import datetime
import glob
import concurrent.futures

import math
import numpy as np
import obspy
import threading




def generate_spectra(midtime, substream, sampling_rate, thread):
    
    '''
    Use i (CPU #) and c (# spectra generated by the CPU) to
    generate spectra for a data window and save it to a list
    unique for the CPU.
    v2 - do this outside of the function
    '''
    
    global spectrum_list               
    
    # Generate spectra
    
    try:
        
        spectrum = np.fft.fft(substream)
                           
        # Save spectrum and metadata (only up to nyquist frequency)
    
        spectrum_list[thread].append([midtime, spectrum[:int(sampling_rate / 2) + 1]])
        
    except:
        
        pass




def spectra_generator(stream_file):
    
    '''
    Calculate spectra for stream. All variables bar stream_file
    are defined prior to the function call.
    '''
    
    global spectrum_list

    # Load the data as an obspy stream object
    # and determine its sampling rate and
    # length in FFT windows

    stream = obspy.read(stream_file)
    
    sampling_rate = stream[0].stats.sampling_rate                
    
    num_windows = int(float(1 / (1 - FFT_window_overlap)) * \
                  (len(stream[0].data) / sampling_rate) / float(FFT_window_length))
    
    start_time = stream[0].stats.starttime
    
    # Filter the stream to remove data that is unresolvable
    # with the given FFT window length
    
    stream.filter('highpass', freq = 1 / float(FFT_window_length))
    
    # Split the stream into windows and calculate their spectra,
    # encorporating window overlap
              
    # First generate the substreams
    
    midtimes = [[] for j in range(num_windows)]
    substreams = [[] for j in range(num_windows)]
    
    print('Separating stream into substreams for FFT calculation')

    for j in range(num_windows):
    
        # Calculate window midtime
        
        midtime = start_time + (j) * (1 - FFT_window_overlap) * FFT_window_length + 0.5 * FFT_window_length
        
        # Trim stream to window
        
        substream = stream.copy()
        substream.trim(starttime = start_time + j * (1 - FFT_window_overlap) * FFT_window_length, 
                       endtime = start_time + j * (1 - FFT_window_overlap) * FFT_window_length + FFT_window_length
                       - 1 / float(sampling_rate))
                       
        # Demean and detrend data in window
                       
        substream.detrend(type = 'demean')
        substream.detrend(type = 'simple')
        
        midtimes[j]= midtime
        substreams[j] = substream[0].data

    # Now generate the stream spectra using multithreading
    
    spectrum_list = [[] for i in range(numthreads)]
    
    count = 0
    threads = [[] for i in range(numthreads)]
    
    print('Calculating substream spectra')
    
    while count <= (int(math.ceil(num_windows / numthreads))):    
        
        for thread in range(numthreads):
            
            # Generate j variable: the index of the data window to process

            j = thread + (count * numthreads)
            
            # Get data from lists
            
            try:
            
                midtime = midtimes[j]
                substream = substreams[j]
                
            except:
                
                break
            
            # Do FFT
          
            p = threading.Thread(target = generate_spectra, args = (midtime, substream, sampling_rate, thread, ))
            threads[thread] = p
            p.start()
        
        for thread in threads:
        
            thread.join()
            
        # Once all jobs complete, increment the count
            
        count += 1
        
        # As the while ... else logic doesn't seem to work,
        # just use an if statement (slow, but functional)
        
        if count == (int(math.ceil(num_windows / numthreads))):
            
            # Save spectrum to disk                            
            
            spectrums_array = np.array(spectrum_list)
            np.save(spectrum_output_directory + str(stream_file.split('/')[-1]) + '_spectrums', spectrums_array)




# Set parameters

## Stream root directory contains individual day-long streams of each station's components
## within julian day directories

stream_root_directory = '/media/sam/61D05F6577F6DB39/SCIENCE/day_volumes_S/'

## Directory to save spectrum files to

spectrum_output_directory = '/home/samto/Spectrums_CRUDE/'

## Seismic component to use in processing

stream_component = 'Z'

## Stations to process

#stream_stations = ['TSNM1', 'TSNM2', 'TSNM3']
stream_stations = ['TSNC1', 'TSNC3', 'TSNL2', 'TSNL3', 'TSNR2', 'TSNR3']

## Start and end dates for processing of day-long seismic streams

start_year = '2016'
start_month = '04'
start_day = '29'

end_year = '2017'
end_month = '06'
end_day = '01'

## Set FFT window length (seconds)

FFT_window_length = 25/250

## Set FFT window overlap (fractional percentage)

FFT_window_overlap = 0

## Number of CPUs to use for multithreading

numthreads = 2

# Convert start and end dates into datetime objects, and get them as julian days in their respective years
    
start_date = datetime.datetime.strptime(start_year + '-' + start_month + '-'+ start_day, '%Y-%m-%d')
end_date = datetime.datetime.strptime(end_year + '-' + end_month + '-'+ end_day, '%Y-%m-%d')

start_date_doy = start_date.timetuple().tm_yday
end_date_doy = end_date.timetuple().tm_yday

# Convert start and end dates into datetime objects, and get them as julian days in their respective years
    
start_date = datetime.datetime.strptime(start_year + '-' + start_month + '-'+ start_day, '%Y-%m-%d')
end_date = datetime.datetime.strptime(end_year + '-' + end_month + '-'+ end_day, '%Y-%m-%d')

start_date_doy = start_date.timetuple().tm_yday
end_date_doy = end_date.timetuple().tm_yday

# Look through data in all streams within the processing window

years = range(int(start_year), int(start_year) + int(end_year) - int(start_year))

for year in years:
    
    for doy in range(366):
        
        if (year == int(start_year)) and (doy < int(start_date_doy)): continue                        
        elif (year == int(end_year)) and (doy > int(end_date_doy)): continue            
        else:

            stream_files = glob.glob(stream_root_directory + 'Y' + str(year) + '/R' + str(doy) + '.01/*')
            stream_files_to_process = []
            
            for stream_file in stream_files:
        
                stream_file_metadata = stream_file.split('/')[-1].split('.')
                component = stream_file_metadata[3][-1]
                station = stream_file_metadata[0]
                
                if component != stream_component: continue
                if station not in stream_stations: continue
        
                stream_files_to_process.append(stream_file)
                
            # Launch a separate python interpreter for each stream's processing
            
            print('Processing stream files:')
            print(stream_files_to_process)
                
            with concurrent.futures.ProcessPoolExecutor() as executor:
                
                executor.map(spectra_generator, stream_files_to_process)