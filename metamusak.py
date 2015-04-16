from rdflib import Graph
from pymediainfo import MediaInfo
from subprocess import check_output 
import pprint
import csv
import re
import os
# path to everything
ringcycle = "/home/davidw/RingCycle/"
# path to rdf folder
rdfdir = ringcycle + "metamusak/"
videos = list()
# graph annotation page turns
caroturns = list()
caroturnreader = csv.reader( open (ringcycle + "data/carolin_pageturns_final.csv", "r"), delimiter=",", quotechar='"')
#5 items: filesize, date, time, page, annotated_by
for line in caroturnreader: 
    caroturns.append(
        {
            "filesize":     line[0],
            "date":         line[1],
            "time":         line[2],
            "page":         line[3],
            "annotated_by": line[4]
        }
    )

# do annotation videos
for opera in os.listdir(ringcycle + 'video'):
    for video in os.listdir(ringcycle + 'video/' + opera):
        if video[0] == ".": 
            continue
        if video.endswith("m4v"): #TODO VERIFY
            continue 
        #mediainfo = check_output(["mediainfo", ringcycle + 'video/' + opera + '/' + video])
       # for line in mediainfo.splitlines():
        mediainfo = MediaInfo.parse(ringcycle + 'video/' + opera + '/' + video)
        thisfile = dict()
        for track in mediainfo.tracks:
            if track.track_type == "General":
                thisfile["rdftool_opera"] = opera
                thisfile["rdftool_filename"] = video
                thisfile["rdftool_filepath"] = ringcycle + "video/" + opera + "/"
                thisfile["duration"] = track.duration
                thisfile["encoded_date"] = track.encoded_date
                thisfile["file_size"] = track.file_size
                thisfile["file_name"] = track.file_name
                thisfile["format"] = track.format
            if track.track_type == "Video":
                thisfile["video_codec"] = track.codec
                thisfile["video_codec_url"] = track.codec_url
                thisfile["video_display_aspect_ratio"] = track.display_aspect_ratio
                thisfile["video_format"] = track.format
                thisfile["video_bit_depth"] = track.bit_depth
                thisfile["video_bit_rate"] = track.bit_rate
                thisfile["video_sampling_rate"] = track.sampling_rate
                thisfile["video_resolution"] = track.resolution
                thisfile["video_height"] = track.height
                thisfile["video_width"] = track.width
                thisfile["video_duration"] = track.duration
            if track.track_type == "Audio":
                thisfile["audio_bit_rate"] = track.bit_rate
                thisfile["audio_codec"] = track.codec
                thisfile["video_duration"] = track.duration
        videos.append(thisfile)

#for v in videos:
#    for k in v:
#        print k, ": ", v[k]


# TIMELINE LOGIC
# Annotation page turn timeline:
# We need to bootstrap durations
# Do this by:
#   - Figure out which pages go with which opera
#   - For each opera
#       - For each page
#           - Add a "duration" which is the timestamp of the NEXT page minus the timestamp of THIS page
#           - If there is no next page, make the duration a constant?


# Build the RDF graph
g = Graph()
for v in videos:
    for k in v:
        g.parse(data='<http://example.com/{filename}> <http://example.com/{key}> "{value}" .'.format(filename = v["file_name"], key = k, value = v[k]), format="turtle")

result = g.query('CONSTRUCT { ?track ?p ?o } WHERE { BIND(<http://example.com/BDMV> as ?track) . ?track ?p ?o }')
print result.serialize(format="turtle")
