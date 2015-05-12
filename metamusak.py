from rdflib import Graph
from pymediainfo import MediaInfo
from pprint import pprint
from datetime import datetime, timedelta
import urllib
import random
import string
import csv
import re
import os

def calculateTimelineOffsets(performanceTimestamps):
    performanceOffsets = dict()
    for p in performanceTimestamps:
        offsets = dict()
        offsets["perfid"] = p["uid"]
        performanceAudioSynctime = datetime.strptime(p["performanceAudio"], "%d/%m/%Y %H:%M:%S")
        MMRESynctime = datetime.strptime(p["MMRE"],"%d/%m/%Y %H:%M:%S") 
        freehandAnnotationLayer1Synctime = datetime.strptime(p["freehandAnnotationLayer1"], "%d/%m/%Y %H:%M:%S.%f")
        # we declare performanceAudio to be our ground truth universal timeline
        # thus, figure out difftime between that and the others
        offsets["basetime"] = performanceAudioSynctime
        freehandAnnotationVideo = offsets["basetime"] #FIXME figure out what to do here
        annotatorVideo = offsets["basetime"] #FIXME figure out what to do here:
        # TODO figure out annotator video
        # 1. figure out starting timestamps
        # 2. Add on the annotatorVideoOffset 
        # 3. Subtract performanceAudioSynctime from the result
        # 4. Store seconds of resulting timedelta in offsets["annotatorVideo"]


        offsets["performanceAudio"] = 0;
        if p["annotatorAudio"]: # we only have it for Rheingold
            offsets["annotatorAudio"] = generateTimeDelta(datetime.strptime(p["annotatorAudio"], "%H:%M:%S"))
        else:
            offsets["annotatorAudio"] = "None"
        offsets["annotatorVideo"] = getOffsetSeconds(annotatorVideo, offsets["basetime"])
        offsets["MMRE"] = getOffsetSeconds(MMRESynctime, offsets["basetime"])
        offsets["freehandAnnotationLayer1"] = getOffsetSeconds(freehandAnnotationLayer1Synctime, offsets["basetime"]) #FIXME fhAL1St also has microseconds...
        offsets["freehandAnnotationVideo"] = getOffsetSeconds(freehandAnnotationVideo, offsets["basetime"])
        
        performanceOffsets[offsets["perfid"]] = offsets
    return performanceOffsets

def generateTimeDelta(theTime):
    # return the hours, minutes, and seconds of a datetime object as a timedelta
    return timedelta(hours = int(datetime.strftime(theTime, "%H")), minutes = int(datetime.strftime(theTime, "%M")), seconds = int(datetime.strftime(theTime, "%S")))

def getOffsetSeconds(a, b):
    # to get over weird timedelta behaviour 
    # when subtracting a later from an earlier value
    return (b-a).seconds if a<b else (b-a).seconds*-1

def uri(uri):
    # adorn the input with < and > tags (so its treated as a ttl URI)
    return "<" + uri + ">"

def lit(literal):
    # adorn the input with " and " (so its treated as a ttl literal)
    return '"' + str(literal) + '"'

def uid():
    # return a unique-ish short identifier...
    # sample space of 64^8 (2.8e14), should allow millions of strings without collisions
    return ''.join([random.choice(string.ascii_letters+string.digits+'-_') for ch in range(8)])
    
def parseScore(g, performances, filebase, rdfbase) :
    for p in performances:
        perfid = p["uid"]
        perfuri = rdfbase + perfid
        sourcedir = filebase + "performance/" + perfid + "/musicalmanifestation/score"
        for page in os.listdir(sourcedir):
            if page.endswith(".jpg"):  # only jpg files - TODO make this accept other conceivable suffixes, e.g. JPG, jpeg, JPEG, png? etc
                scoretemplate = open(filebase + "metamusak/templates/score.ttl", "r")
                sc = scoretemplate.read()
                sc = sc.format(
                        conceptScore = uri(perfuri + "/musicalmanifestation/conceptScore"),
                        score = uri(perfuri + "/musicalmanifestation/score"),
                        pageOfScore = uri(perfuri + "/musicalmanifestation/score/" + urllib.quote(os.path.splitext(page)[0])),
                        MusicalManifestationRealizationEvent = uri(perfuri + "annotation/pageturn/realization") #FIXME check this
                )

                g.parse(data=sc, format="turtle")
                    

def parsePerformance(g, performances, filebase, rdfbase, offsets) :
    for p in performances:
        perfid = p["uid"]
        perfuri = rdfbase + perfid
        perftemplate = open(filebase + "metamusak/templates/performance.ttl", "r")
        perf = perftemplate.read()
        perf = perf.format(
                ConstructStart = "", 
                ConstructEnd = "",
                digitalSignal = "", # FIXME for construct
                performance = uri(perfuri), 
                Agent1 = uri(p["conductorID"]), 
                Agent2 = uri(p["performerID"]), 
                Agent3 = uri(p["composerID"]),
                Agent4 = uri(p["arrangerID"]),
                Agent5 = uri(p["annotatorID"]),
                Agent6 = uri(p["listenerID"]), 
                conceptScore = uri(perfuri + "/musicalmanifestation/conceptScore"),
                score = uri(perfuri + "/musicalmanifestation/score"),
                musicalWork = uri(p["workID"]), 
                workTitle = lit(p["workTitle"]),
                MMRE_offset = lit(offsets[perfid]["MMRE"]),
                performanceAudio_offset = lit(offsets[perfid]["performanceAudio"]),
                MasterTimeLine = uri(perfuri + "/timelines/master"),
                MMRETimeLine = uri(perfuri + "/timelines/MMRE"),
                performanceTimeLine = uri(perfuri + "/timelines/performance"),
                performanceTimeLineMapMMRE = uri(perfuri + "/timelines/performanceMapMMRE"),
                performanceTimeLineMapPerformanceAudio = uri(perfuri + "/timelines/performanceMapPerformanceAudio"),
                performanceAudioTimeLine = uri(perfuri + "/timelines/performanceAudio")
        )
    
        g.parse(data=perf, format="turtle")

def parseAnnotator(g, performances, filebase, rdfbase, offsets):
    annotatorTemplate = open(filebase + "metamusak/templates/annotator.ttl", "r")
    anno = annotatorTemplate.read()
    for p in performances:
        anno = anno.format(
                Agent5=uri(p["annotatorID"]),
                Agent5Name = lit(p["annotatorName"]),
                MasterTimeLine = uri(p["performanceID"] + "/timelines/master"),
                annotatorActivityTimeLine = uri(p["performanceID"] + "/timelines/annotatorActivity"),
                annotatorAudioTimeLine = uri(p["performanceID"] + "/timelines/annotatorAudio"),
                annotatorAudio_offset = lit(offsets[p["uid"]]["annotatorAudio"]),
                annotatorVideoTimeLine= uri(p["performanceID"] + "/timelines/annotatorVideo"),
                annotatorVideo_offset = lit(offsets[p["uid"]]["annotatorVideo"]),
                annotatorTimeLineMapAnnotatorAudio = uri(p["performanceID"] + "/timelines/annotatorMapAnnotatorAudio"),
                annotatorTimeLineMapAnnotatorVideo = uri(p["performanceID"] + "/timelines/annotatorMapAnnotatorVideo"),
                annotatorTimeLineMapFreehandAnnotationLayer1 = uri(p["performanceID"] + "/timelines/annotatorTimeLineMapFreehandAnnotationLayer1"),
                annotatorTimeLineMapFreehandAnnotationVideo = uri(p["performanceID"] + "/timeline/annotatorTimeLineMapFreehandAnnotationVideo"),
                freehandAnnotationLayer1TimeLine = uri(p["performanceID"] + "/timelines/freehandAnnotationLayer1"),
                freehandAnnotationLayer1_offset = lit(offsets[p["uid"]]["freehandAnnotationLayer1"]),
                freehandAnnotationVideoTimeLine = uri(p["performanceID"] + "/timelines/freehandAnnotationVideo"),
                freehandAnnotationVideo_offset = lit(offsets[p["uid"]]["freehandAnnotationVideo"])
        )
        g.parse(data=anno, format="turtle")


def parsePerformanceAudio(g, performances, filebase, rdfbase):                
    performanceAudioTemplate = open(filebase + "metamusak/templates/performanceAudio.ttl", "r")
    perfau = performanceAudioTemplate.read()
    for p in performances:
        sourcedir =  filebase + "performance/" + p["uid"] + "/musicalmanifestation/"
        perfuri = rdfbase + "performance/" + p["uid"]
        for audiofname in os.listdir(sourcedir):
            if audiofname.endswith(".mp3"):
                # found some annotator audio)!
                mediainfo = getMediaInfo(sourcedir + audiofname)
                for key in mediainfo:
                    if mediainfo[key] is None:
                        continue # skip non-values
                query = perfau.format(
                        performance = uri(perfuri),
                        performanceAudio = uri(perfuri + "/musicalmanifestation/" + urllib.quote(os.path.splitext(audiofname)[0])), # cut off the ".mp3" suffix
                        digitalSignal = uri(perfuri + "/musicalmanifestation/" + urllib.quote(audiofname)),
                        digitalSignalIntervalStart = lit(mediainfo["date"]),
                        digitalSignalIntervalDuration = lit(mediainfo["duration"]),
                        performanceAudioTimeLine = uri(perfuri + "/timelines/performanceAudio"),
                        performanceTimeLine = uri(perfuri + "/timelines/performanceTimeLine"),
                        substituteAudio = uri(perfuri + "/musicalmanifestation/" + urllib.quote(os.path.splitext(audiofname)[0]) + "_sub") #FIXME clarify
                )
                g.parse(data=query, format="turtle")

def parseSubstituteAudio(g, performances, filebase, rdfbase):                
    substituteAudioTemplate = open(filebase + "metamusak/templates/substituteAudio.ttl", "r")
    perfau = substituteAudioTemplate.read()
    for p in performances:
        sourcedir =  filebase + "performance/" + p["uid"] + "/musicalmanifestation/"
        perfuri = rdfbase + "performance/" + p["uid"]
        for audiofname in os.listdir(sourcedir):
            if audiofname.endswith(".mp3"):
                # found some annotator audio)!
                mediainfo = getMediaInfo(sourcedir + audiofname)
                for key in mediainfo:
                    if mediainfo[key] is None:
                        continue # skip non-values
                query = perfau.format(
                        performance = uri(perfuri),
                        performanceAudio = uri(perfuri + "/musicalmanifestation/" + urllib.quote(os.path.splitext(audiofname)[0])), # cut off the ".mp3" suffix
                        substituteAudio = uri(perfuri + "/musicalmanifestation/" + urllib.quote(os.path.splitext(audiofname)[0]) + "sub") #FIXME clarify
                )
                g.parse(data=query, format="turtle")

def parseAnnotatorAudio(g, performances, filebase, rdfbase):
    annotatorAudioTemplate = open(filebase + "metamusak/templates/annotatorAudio.ttl", "r")
    anno = annotatorAudioTemplate.read()
    for p in performances:
        sourcedir =  filebase + "performance/" + p["uid"] + "/annotation/audio/"
        perfuri = rdfbase + "performance/" + p["uid"]
        for audiofname in os.listdir(sourcedir):
            if audiofname.endswith(".m4a"):
                # found some annotator audio!
                mediainfo = getMediaInfo(sourcedir + audiofname)
                for key in mediainfo:
                    if mediainfo[key] is None:
                        continue # skip non-values
                query = anno.format(
                        performance = uri(perfuri),
                        Agent5 = uri(p["annotatorID"]),
                        annotatorAudio = uri(perfuri + "/annotation/audio/" + urllib.quote(os.path.splitext(audiofname)[0])), # cut off the file suffix
                        annotatorAudioBody = uri(perfuri + "/annotation/audio/" + urllib.quote(audiofname)),
                        annotatorAudioBodyIntervalStart = lit(mediainfo["date"]),
                        annotatorAudioBodyIntervalDuration = lit(mediainfo["duration"]),
                        bitrate = lit(mediainfo["averageBitRate"]),
                        dateCreated = lit(mediainfo["date"]),
                        annotatorActivityTimeLine = uri(perfuri + "/timelines/annotatorActivity"),
                        annotatorAudioTimeLine = uri(perfuri + "/timelines/annotatorAudio"),
                    )
                g.parse(data=query, format="turtle")


        # note: files may only be available for some of the performances
        # e.g. in our case, Rheingold
        # so have to check for their existence before writing sidecart

def getMediaInfo(mediaFile):
    mediainfo = MediaInfo.parse(mediaFile)
    thisfile = dict()
    for track in mediainfo.tracks:
        if track.track_type == "General":
#                thisfile["rdftool_opera"] = opera
#                thisfile["rdftool_filename"] = video
#                thisfile["rdftool_filepath"] = ringcycle + "video/" + opera + "/"
            thisfile["duration"] = str(track.duration * .001)
            thisfile["date"] = track.file_last_modification_date
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

def mintRequiredURIs(thisPerformance):
    #FIXME do something useful
    return thisPerformance



if __name__ == "__main__": 
    # physical path
    ringcycle = "/home/davidw/MetaRingCycle/"
    perfbase = ringcycle + "performance/"
    # rdf path
    rdfbase = "http://performance.data.t-mus.org/performance/" 

    userinputfile = csv.reader(open(ringcycle + "metamusak/user_input.csv", "rU"), delimiter = ",", quotechar = '"')
    userinputrows = list()
    userinputfields = list()
    for ix, line in enumerate(userinputfile):
        if ix == 0: # header row - populate fields
            for field in line:
                userinputfields.append(field)
        else : # content row: fill in fields for this performance
            thisPerformance = dict()
            for ix, field in enumerate(userinputfields):
                thisPerformance[field] = line[ix]
            # mint any URIs not provided by the user...
            thisPerformance = mintRequiredURIs(thisPerformance)
            userinputrows.append(thisPerformance)
    for p in userinputrows:
        # determine the UID for this performance, i.e. the <UID> in  /performance/<UID>
        p["uid"] = p["performanceID"][p["performanceID"].rindex("/")+1:]
    syncTimestampsFile = csv.reader(open(ringcycle + "metamusak/syncTimestamps.csv", "rU"), delimiter = ",", quotechar = '"')
    syncTimestamps = list()
    syncTimestampFields = list()
    for ix, line in enumerate(syncTimestampsFile):
        if ix == 0: # header row - populate fields
            for field in line:
                syncTimestampFields.append(field)
        else: # content row - fill in fields for this performance
            performanceTimestamps = dict()
            for ix, field in enumerate(syncTimestampFields):
                performanceTimestamps[field] = line[ix]
            syncTimestamps.append(performanceTimestamps)
    for p in syncTimestamps:
        # determine the UID for this performance, i.e. the <UID> in  /performance/<UID>
        p["uid"] = p["performanceID"][p["performanceID"].rindex("/")+1:]
    offsets = calculateTimelineOffsets(syncTimestamps)
    g = Graph()
    parseScore(g, userinputrows, ringcycle, rdfbase)
    parseAnnotator(g, userinputrows, ringcycle, rdfbase, offsets)
    parsePerformance(g, userinputrows, ringcycle, rdfbase, offsets) 
    parseAnnotatorAudio(g, userinputrows, ringcycle, rdfbase)
    parsePerformanceAudio(g, userinputrows, ringcycle, rdfbase)
    parseSubstituteAudio(g, userinputrows, ringcycle, rdfbase)
    print g.serialize(format="turtle")


