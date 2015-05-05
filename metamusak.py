from rdflib import Graph
from pymediainfo import MediaInfo
import pprint
import csv
import re
import os

def parsePerformances(g, performances, metamusak, rdfbase) :
    for performance in performances:
        perfid = performance["uid"]
        perfuri = rdfbase + perfid
        perftemplate = open(metamusak + "/templates/performance.ttl", "r")
        perf = perftemplate.read()
        perf = perf.format(
                ConstructStart = "", 
                ConstructEnd = "",
                Performance1 = perfuri, 
                Agent6 = performance["listener"], 
                Agent2 = performance["performerID"], 
                Agent1 = performance["conductorID"], 
                MusicalWork1 = performance["workID"], 
                WorkTitle = performance["title"])
        g.parse(data=perf, format="turtle")

def generatePerformances(g, perfbase, performances, metamusak, rdfbase) :
    for performance in performances:
        perfid = performance["uid"]
        sidecart = open(perfbase + perfid + "/performance.ttl", "w")
        perfuri = rdfbase + perfid
        perftemplate = open(metamusak + "/templates/performance.ttl", "r")
        perf = perftemplate.read()
        perf = perf.format(
                ConstructStart = "CONSTRUCT {", 
                ConstructEnd = "} WHERE {}",
                Performance1 = perfuri, 
                Agent6 = performance["listener"], 
                Agent2 = performance["performerID"], 
                Agent1 = performance["conductorID"], 
                MusicalWork1 = performance["workID"], 
                WorkTitle = performance["title"])
        qres = g.query(perf)
        sidecart.write(qres.serialize(format="turtle"))

def parseAnnotatorVideos(filebase, rdfbase, userinput, metamusak):
    annotatortemplate = open(metamusak + "/templates/annotator.ttl", "r")
    anno = annotatortemplate.read()
    for row in userinput:
        performance = row["uid"]
        # each act...
        actsdir = filebase + "{0}/acts/".format(performance)
        actsrdf = rdfbase + "{0}/acts/".format(performance)
        for act in os.listdir(actsdir):
            if act[0] == ".":
                continue # skip hidden
            video = actsdir + act + "/annotator.mov"
            videordf = actsrdf + act + "/annotator"
            mediainfo = getMediaInfo(video)
            for key in mediainfo:
                if mediainfo[key] is None: 
                    continue # skip blank values
                query = anno.format(
                            ConstructStart = "",
                            ConstructEnd = "",
                            Body3 = "<" + videordf + ">", 
                            annotationPerformance = "<"+actsrdf + act+">", 
                            duration = '"'+mediainfo["duration"]+'"',
                            bitrate = '"'+mediainfo["averageBitRate"]+'"',
                            frameSize = '"'+mediainfo["frameSize"]+'"',
                            frameRate = '"'+mediainfo["frameRate"]+'"',
                            dateCreated = '"'+mediainfo["date"]+'"',
                            videoformat = '"'+mediainfo["videoformat"]+'"'
                        )
                g.parse(data=query, format="turtle")
                print g.serialize(format="turtle")

def generateAnnotatorVideos(filebase, rdfbase, userinput, metamusak):
    annotatortemplate = open(metamusak + "/templates/annotator.ttl", "r")
    anno = annotatortemplate.read()
    for row in userinput:
        performance = row["uid"]
        # each act...
        actsdir = filebase + "{0}/acts/".format(performance)
        actsrdf = rdfbase + "{0}/acts/".format(performance)
        for act in os.listdir(actsdir):
            video = actsdir + act + "/annotator.mov"
            videordf = actsrdf + act + "/annotator"
            sidecart = open(actsdir + act + "/annotator.ttl", 'w')
            constructQ = anno.format(
                            ConstructStart = "CONSTRUCT { ",
                            Body3 = "<" + videordf + ">", 
                            annotationPerformance = "?annoPerformance",
                            duration = "?duration",
                            bitrate = "?bitrate",
                            frameSize = "?frameSize",
                            frameRate = "?frameRate",
                            dateCreated = "?dateCreated",
                            videoformat = "?videoformat",
                            ConstructEnd = """
                                }} WHERE {{
                                  {Body3} mo:records ?annoPerformance;
                                          ma:format ?videoformat; 
                                          ma:duration ?duration ;
                                          ma:averageBitRate ?bitrate ;
                                          ma:frameSize ?frameSize ;
                                          ma:frameRate ?frameRate ;
                                          ma:date ?dateCreated .
                                }}""".format(Body3 = "<" + videordf + ">"),
                            )
            print constructQ
            rdfresult = g.query(constructQ)
            print rdfresult
            sidecart.write(rdfresult.serialize(format="turtle"))
            #TODO Add some nice exception catching here
            sidecart.close()

def getMediaInfo(mediaFile):
    mediainfo = MediaInfo.parse(mediaFile)
    thisfile = dict()
    for track in mediainfo.tracks:
        if track.track_type == "General":
#                thisfile["rdftool_opera"] = opera
#                thisfile["rdftool_filename"] = video
#                thisfile["rdftool_filepath"] = ringcycle + "video/" + opera + "/"
            thisfile["duration"] = str(track.duration)
            thisfile["date"] = track.encoded_date
#                thisfile["file_size"] = track.file_size
            thisfile["title"] = track.file_name
            thisfile["format"] = track.format
            thisfile["averageBitRate"] = str(track.overall_bit_rate)
        if track.track_type == "Video":
#                thisfile["video_codec"] = track.codec
#                thisfile["video_codec_url"] = track.codec_url
#                thisfile["video_display_aspect_ratio"] = track.display_aspect_ratio
            thisfile["videoformat"] = track.format
#                thisfile["video_bit_depth"] = track.bit_depth
#                thisfile["video_bit_rate"] = track.bit_rate
            thisfile["frameRate"] = str(track.frame_rate)
            thisfile["frameSize"] = str(track.width) + 'x' + str(track.height)
#                thisfile["video_resolution"] = track.resolution
#                thisfile["video_height"] = track.height
#                thisfile["video_width"] = track.width
#                thisfile["video_duration"] = track.duration
        if track.track_type == "Audio":
#                thisfile["audio_bit_rate"] = track.bit_rate
#                thisfile["audio_codec"] = track.codec
#                thisfile["video_duration"] = track.duration
            thisfile["audioformat"] = track.format
    return thisfile


if __name__ == "__main__":

    # physical path
    ringcycle = "/home/davidw/MetaRingCycle/"
    perfbase = ringcycle + "performance/"
    performances = os.listdir(perfbase)
    # rdf path
    rdfbase = "http://performance.data.t-mus.org/performance/" 

    
    inputfile = csv.reader(open(ringcycle + "metamusak/user_input.csv", "rU"), delimiter = ",", quotechar = '"')
    inputrows = list()
    inputfields = list()
    for ix, line in enumerate(inputfile):
        if ix == 0: # header row - populate fields
            for field in line:
                inputfields.append(field)
        else : # content row: fill in fields for this performance
            thisPerformance = dict()
            for ix, field in enumerate(inputfields):
                thisPerformance[field] = line[ix]
            inputrows.append(thisPerformance)
    g = Graph()
    
    # parse into graph
    parsePerformances(g, inputrows, ringcycle + "metamusak", rdfbase)
    parseAnnotatorVideos(perfbase, rdfbase, inputrows, ringcycle + "metamusak")
   
    # generate sidecarts
    generatePerformances(g, perfbase, inputrows, ringcycle + "metamusak", rdfbase)
    generateAnnotatorVideos(perfbase, rdfbase, inputrows, ringcycle + "metamusak")
