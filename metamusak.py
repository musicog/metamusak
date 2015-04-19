from rdflib import Graph
from pymediainfo import MediaInfo
from subprocess import check_output 
import pprint
import csv
import re
import os

g = Graph() # The Graph Dracula

def generateSidecarts(performances, templates, filebase, rdfbase):
    # for each performance -- replace this with list of ids from magic spreadsheet 
    for performance in performances:
        # annotator videos
        annotatordir = filebase + "{0}/annotator/".format(performance)
        annotatorrdf = rdfbase + "{0}/annotator/".format(performance)
        for video in os.listdir(annotatordir):
            videobase = os.path.splitext(video)[0]
            if video[0] == ".": #skip hidden files
                continue
            mediainfo = getMediaInfo(annotatordir + video)
            for key in mediainfo:
                if mediainfo[key] is None: 
                    continue # skip blank values
                g.parse(data='<{uri}> <{key}> "{value}" .'.format(uri = annotatorrdf + videobase, key = key, value = mediainfo[key]), format="turtle")
            sidecart = open(annotatordir + videobase + ".ttl", 'w')
            constructQ = templates["annotator"].format(uri = annotatorrdf + videobase, performance = rdfbase + performance)
            rdfresult = g.query(constructQ)
            sidecart.write(rdfresult.serialize(format="turtle"))
            #TODO Add some nice exception catching here
            print "Wrote to {0}".format(annotatordir + videobase + ".ttl")
            sidecart.close()

def getMediaInfo(mediaFile):
    mediainfo = MediaInfo.parse(mediaFile)
    thisfile = dict()
    for track in mediainfo.tracks:
        if track.track_type == "General":
#                thisfile["rdftool_opera"] = opera
#                thisfile["rdftool_filename"] = video
#                thisfile["rdftool_filepath"] = ringcycle + "video/" + opera + "/"
            thisfile["http://www.w3.org/ns/ma-ont#duration"] = track.duration
            thisfile["http://www.w3.org/ns/ma-ont#date"] = track.encoded_date
#                thisfile["file_size"] = track.file_size
            thisfile["http://www.w3.org/ns/ma-ont#title"] = track.file_name
            thisfile["http://www.w3.org/ns/ma-ont#format"] = track.format
            thisfile["http://www.w3.org/ns/ma-ont#averageBitRate"] = track.overall_bit_rate
        if track.track_type == "Video":
#                thisfile["video_codec"] = track.codec
#                thisfile["video_codec_url"] = track.codec_url
#                thisfile["video_display_aspect_ratio"] = track.display_aspect_ratio
            thisfile["http://www.w3.org/ns/ma-ont#format"] = track.format
#                thisfile["video_bit_depth"] = track.bit_depth
#                thisfile["video_bit_rate"] = track.bit_rate
            thisfile["http://www.w3.org/ns/ma-ont#frameRate"] = track.frame_rate
            thisfile["http://www.w3.org/ns/ma-ont#frameSize"] = str(track.width) + 'x' + str(track.height)
#                thisfile["video_resolution"] = track.resolution
#                thisfile["video_height"] = track.height
#                thisfile["video_width"] = track.width
#                thisfile["video_duration"] = track.duration
        if track.track_type == "Audio":
#                thisfile["audio_bit_rate"] = track.bit_rate
#                thisfile["audio_codec"] = track.codec
#                thisfile["video_duration"] = track.duration
            thisfile["http://www.w3.org/ns/ma-ont#format"] = track.format
    return thisfile


if __name__ == "__main__":
    templates = { # TODO read these from an external directory? perhaps?
        "annotator": #annotator video
            """
            PREFIX dct: <http://purl.org/dc/terms/>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            CONSTRUCT {{ 
                <{uri}> rdfs:comment "TODO More stuff on how this fits in to the performance / series" ;
                      dct:isPartOf <{performance}> .
                <{uri}> ?p ?o .
            }} WHERE {{ 
                <{uri}> ?p ?o .
            }}
            """
    }

    # physical path
    ringcycle = "/home/davidw/MetaRingCycle/performance/"
    performances = os.listdir(ringcycle)
    # rdf path
    rdfbase = "http://performance.data.t-mus.org/performance/" 
    generateSidecarts(performances, templates, ringcycle, rdfbase)
    print "Done!"
