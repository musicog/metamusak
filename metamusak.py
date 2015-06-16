from rdflib import Graph
from pymediainfo import MediaInfo
from pprint import pprint
from datetime import datetime, timedelta
from warnings import warn
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

        offsets["performanceAudio"] = 0;
        if p["annotatorAudio"]: # we only have it for Rheingold
            offsets["annotatorAudio"] = generateTimeDelta(datetime.strptime(p["annotatorAudio"], "%H:%M:%S"))
        else:
            offsets["annotatorAudio"] = "None"

        # annotatorVideo: we have number of seconds between start of video file and clap event
        # for all nights except Walkuere
        if p["annotatorVideo"]: # FIXME currently missing the clap offset for Walkuere...
            # therefore, subtract annotatorVideo syncTimestamp (as timedelta) from basetime to get annotatorVideo time
            annotatorVideoSynctime = offsets["basetime"] - generateTimeDelta(datetime.strptime(p["annotatorVideo"], "%H:%M:%S"))
            offsets["annotatorVideo"] = getOffsetSeconds(annotatorVideoSynctime, offsets["basetime"])
        else:  #FIXME THIS IS A LIE -- we need to figure out the correct value for Walkuere
            offsets["annotatorVideo"] = 0
        offsets["freehandAnnotationLayer1"] = getOffsetSeconds(freehandAnnotationLayer1Synctime, offsets["basetime"]) #FIXME fhAL1St also has microseconds...
        offsets["freehandAnnotationVideo"] = getOffsetSeconds(freehandAnnotationVideo, offsets["basetime"])
        offsets["MMRE"] = getOffsetSeconds(MMRESynctime, offsets["basetime"])
        performanceOffsets[offsets["perfid"]] = offsets
    return performanceOffsets

def generateTimeDelta(theTime):
    # return the hours, minutes, and seconds of a datetime object as a timedelta
    return timedelta(hours = int(datetime.strftime(theTime, "%H")), minutes = int(datetime.strftime(theTime, "%M")), seconds = int(datetime.strftime(theTime, "%S")))

def getOffsetSeconds(a, b):
    # to get over weird timedelta behaviour 
    # when subtracting a later from an earlier value
    return (b-a).seconds if a<b else (a-b).seconds*-1

def uri(uri):
    # adorn the input with < and > tags (so it's treated as a ttl URI)
    return "<" + uri + ">"

def lit(literal):
    # adorn the input with " and " (so it's treated as a ttl literal)
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
        
        # read in performance page turns
        # note regarding the CSV files produced by Richard's tool:
        # * The last page before the end of an act is NOT encoded in the same way as the others
        #   instead its turn time is encoded as an act ending event (e.g. "act 1 ends")
        # * also, for some reason, act starts and ends are encoded to the second, whereas all other pageturns are
        #   to the millisecond. 
        pageturnsfile = csv.reader(open(filebase + "performance/" + perfid + "/musicalmanifestation/pageturn/performance.csv", "r"), delimiter=",", quotechar='"')
        pageturns = dict()
        pageturnFields = list()
        prevTime = "" # used in MMRE duration calculation
        prevPage = 0 # used to calculate the page number for "act ends" (see note above)
        for ix, line in enumerate(pageturnsfile):
            if ix <= 2: # skip headers and sync claps
                next
            else: # content row - fill in fields
                m = re.match("page \w+-(\d+) ends", line[0])
                n = re.match("act \d ends", line[0])
                if m or n: # act ends are just page turns in richard's tool
                    thisPage = dict()
                    #FIXME URGENTLY: Address the pagenum discrepancy between Richard and Carolin (see R script)
                    if m:
                        thisPage["pageNum"] =  int(m.group(1))
                    else: 
                        thisPage["pageNum"] = prevPage+1
                    thisPage["opera"] = line[1]
                    thisPage["act"] = line[2]
                    try:
                        thisPage["turntime"] = datetime.strptime(line[4], "%Y-%m-%d %H:%M:%S.%f")
                    except:
                    #FIXME for Richard: tool specifies pageturns to millisecond but act starts/ends to the second
                        thisPage["turntime"] = datetime.strptime(line[4], "%Y-%m-%d %H:%M:%S")
                    # each page is preceded in the file by a timestamped event of some sort...
                    # even the first page, as there is other timestamped info in the file (e.g. start of act)
                    # we can rely on this when calculating MMRE durations
                    thisPage["starttime"] = prevTime
                    thisPage["duration"] = thisPage["turntime"] - thisPage["starttime"] 
                    pageturns[thisPage["pageNum"]] = thisPage
                    prevPage = thisPage["pageNum"] # track for when we reach an act ends event
                # regardless of event type, record the timestamp for MMRE duration calculation
                try: 
                    prevTime = datetime.strptime(line[4], "%Y-%m-%d %H:%M:%S.%f")
                except: 
                    prevTime = datetime.strptime(line[4], "%Y-%m-%d %H:%M:%S")

        # now work through the page image files
        for page in os.listdir(sourcedir):
            if page.endswith(".jpg"):  # only jpg files - TODO make this accept other conceivable suffixes, e.g. JPG, jpeg, JPEG, png? etc
                m = re.match("\w+-(\d+).jpg", page)
                pagenum = int(m.group(1))
                if pagenum in pageturns:
                    # set up score.ttl
                    scoreTemplate = open(filebase + "metamusak/templates/score.ttl", "r")
                    sc = scoreTemplate.read()
                    sc = sc.format(
                            conceptScore = uri(perfuri + "/musicalmanifestation/conceptScore"),
                            score = uri(perfuri + "/musicalmanifestation/score"),
                            pageOfScore = uri(perfuri + "/musicalmanifestation/score/" + urllib.quote(os.path.splitext(page)[0])),
                            MusicalManifestationRealizationEvent = uri(perfuri + "/musicalmanifestation/pageturn/" + str(pagenum)) #FIXME check this
                    )
                    # set up performancePageturn.ttl 
                    performancePageturnTemplate = open(filebase + "metamusak/templates/performancePageturn.ttl")
                    pt = performancePageturnTemplate.read()
                    pt = pt.format(
                            MusicalManifestationRealizationEvent = uri(perfuri + "/musicalmanifestation/pageturn/" + str(pagenum)), #FIXME check this
                            pageOfScore = uri(perfuri + "/musicalmanifestation/score/" + urllib.quote(os.path.splitext(page)[0])),
                            Agent6=uri(p["listenerID"]),
                            MMReventIntervalStart = lit(pageturns[pagenum]["starttime"]),
                            MMReventIntervalDuration = lit(pageturns[pagenum]["duration"]),
                            performanceTimeLine = uri(perfuri + "/timelines/performance"),
                            performanceTimeLineMapMMRE = uri(perfuri + "/timelines/performanceMapMMRE")
                    )
                           
                    # now ingest both templates    
                    g.parse(data=sc, format="turtle")
                    g.parse(data=pt, format="turtle")
                else: # don't produce any RDF for pages missing performance pageturn data (e.g. end of Walkuere)
                    warn("Warning: don't have performance page turn info for page {0}, performance {1}".format(pagenum, perfid))

def parseAnnotatedScore(g, performances, filebase, rdfbase):
    for p in performances:
        perfid = p["uid"]
        perfuri = rdfbase + perfid
        
        # parse in annotation page turns
        pageturnsfile = csv.reader(open(filebase + "performance/" + perfid + "/annotation/pageturn/annotation.csv", "r"), delimiter=",", quotechar='"')
        pageturns = dict()
        pageturnFields = list()
        prevTime = "" # used in freehandAnnotationLayer1 duration calculation
        for ix, line in enumerate(pageturnsfile):
            if ix <= 1: #skip header and first page (which is just an empty title)
                if ix == 1: # bootstrap prevTime for duration calculation from initial page
                    prevTime = datetime.strptime(line[1] + " " + line[2], "%d/%m/%Y %H:%M:%S")
                next
            else:
                # content row - fill in fields
                thisPage = dict()
                thisPage["turntime"] = datetime.strptime(line[1] + " " + line[2], "%d/%m/%Y %H:%M:%S")
                thisPage["starttime"] = prevTime
                thisPage["duration"] = thisPage["turntime"] - thisPage["starttime"]
                prevTime = thisPage["turntime"]
                thisPage["datafile"] = line[3]
                m = re.match("(\w+page(\d+)).csv", line[3])
                thisPage["basename"] = m.group(1)
                thisPage["pagenum"] = int(m.group(2))
                pageturns[thisPage["pagenum"]] = thisPage
        
        score1sourcedir = filebase + "performance/" + perfid + "/annotation/score1"
        score2sourcedir = filebase + "performance/" + perfid + "/annotation/score2"
        for page in os.listdir(score1sourcedir):
            m = re.match("opera\d_PG \((\d+)\).jpg", page)
            if m:
                basename = os.path.splitext(page)[0]
                ## DO LAYER 1 SCORE
                pagenum = int(m.group(1))
                try: 
                    pageturns[pagenum]
                except: 
                    warn("Warning: don't have annotator page turn info for {0}".format(page))
                    continue
                #TODO for musak 2.0: make page numbers and file names consistent between listener and annotator!!!
                # so that the following nonsense isn't necessary:
                pageOfScoreNum = pagenum + int(p["scorePageOffset"])
                pageOfScore = p["operaPrefix"] + "-" + "{0:0>4}".format(pageOfScoreNum)
                annotatedScoreLayer1Template = open(filebase + "metamusak/templates/annotatedScoreLayer1.ttl", "r")
                sc1 = annotatedScoreLayer1Template.read()
                sc1 = sc1.format(
                        pageOfAnnotatedScoreLayer1 = uri(perfuri + "/annotation/score1/" + urllib.quote(basename)),
                        pageOfScore = uri(perfuri + "/musicalmanifestation/score/" + pageOfScore)
                )
                # PARSE IT
                g.parse(data=sc1, format="turtle")


                ## DO LAYER 2 SCORE (png)
                sc2fname = basename + "-live.png"
                sc2basename = basename + "-live"
                if os.path.isfile(score2sourcedir + "/" + sc2fname):
                    # some may not exist, e.g. the first and last blank pages 
                    annotatedScoreLayer2Template = open(filebase + "metamusak/templates/annotatedScoreLayer2.ttl", "r")
                    sc2 = annotatedScoreLayer2Template.read()
                    sc2 = sc2.format(
                        pageOfAnnotatedScoreLayer2 = uri(perfuri + "/annotation/score2/" + urllib.quote(sc2basename)),
                        pageOfAnnotatedScoreLayer1 = uri(perfuri + "/annotation/score1/" + urllib.quote(basename)),
                        freehandAnnotation = uri(perfuri + "/annotation/" + urllib.quote(pageturns[pagenum]["basename"]))
                    )
                    ## DO FREEHAND ANNOTATION
                    freehandAnnotationLayer1Template = open(filebase + "metamusak/templates/freehandAnnotationLayer1.ttl", "r")
                    fh1 = freehandAnnotationLayer1Template.read()
                    fh1 = fh1.format(
                        freehandAnnotationLayer1 = uri(perfuri + "/annotation/" + str(pagenum)),
                        #freehandAnnotationLayer1 = uri(perfuri + "/annotation/" + urllib.quote(pageturns[pagenum]["basename"])),
                        Agent5 = uri(p["annotatorID"]),
                        performance = uri(perfuri),
                        annotatedScoreLayer1 = uri(perfuri + "/annotation/score1/" + urllib.quote(basename)),
                        annotatedScoreLayer2 = uri(perfuri + "/annotation/score2/" + urllib.quote(sc2basename)),
                        annotatorVideo = uri(perfuri + "/annotator/annotator1.mov"),# FIXME
                        freehandAnnotationLayer1IntervalStart = lit(pageturns[pagenum]["starttime"]),
                        freehandAnnotationLayer1IntervalDuration = lit(pageturns[pagenum]["duration"]),
                        annotatorActivityTimeLine = uri(p["performanceID"] + "/timelines/annotatorActivity"),
                        freehandAnnotationLayer1TimeLine = uri(p["performanceID"] + "/timelines/freehandAnnotationLayer1")
                    )
                    # NOW PARSE BOTH
                    g.parse(data=sc2, format="turtle")
                    g.parse(data=fh1, format="turtle")
                        

                

def parsePerformance(g, performances, filebase, rdfbase, offsets):
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
    for p in performances:
        annotatorTemplate = open(filebase + "metamusak/templates/annotator.ttl", "r")
        anno = annotatorTemplate.read()
        anno = anno.format(
                Agent5=uri(p["annotatorID"]),
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
        annotatorTemplate.close()


def parsePerformanceAudio(g, performances, filebase, rdfbase):                
    performanceAudioTemplate = open(filebase + "metamusak/templates/performanceAudio.ttl", "r")
    perfau = performanceAudioTemplate.read()
    for p in performances:
        sourcedir =  filebase + "performance/" + p["uid"] + "/musicalmanifestation/"
        perfuri = rdfbase + p["uid"]
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
        perfuri = rdfbase + p["uid"]
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
        perfuri = rdfbase + p["uid"]
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
   
def parseAnnotatorVideo(g, performances, filebase, rdfbase, offsets):
    annotatorAudioTemplate = open(filebase + "metamusak/templates/annotatorVideo.ttl", "r")
    anno = annotatorAudioTemplate.read()
    for p in performances:
        sourcedir =  filebase + "performance/" + p["uid"] + "/annotator/"
        perfuri = rdfbase + p["uid"]
        for videofname in os.listdir(sourcedir):
            if videofname.endswith(".mov"): #TODO enable other formats
                # found some annotator video!
                mediainfo = getMediaInfo(sourcedir + videofname)
                for key in mediainfo:
                    if mediainfo[key] is None:
                        continue # skip non-values
                query = anno.format(
                        performance = uri(perfuri),
                        Agent5 = uri(p["annotatorID"]),
                        annotatorVideo = uri(perfuri + "/annotator/" + urllib.quote(os.path.splitext(videofname)[0])), # cut off the file suffix
                        annotatorVideoIntervalStart = lit(mediainfo["date"]), # FIXME not correct date
                        annotatorVideoIntervalDuration = lit(mediainfo["duration"]),
                        annotatorActivityTimeLine = uri(perfuri + "/timelines/annotatorActivity"),
                        annotatorVideoTimeLine = uri(perfuri + "/timelines/annotatorVideo"),
                    )
                g.parse(data=query, format="turtle")

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
    #TODO do something useful
    return thisPerformance


def generateAnnotator(g, performances, filebase, rdfbase):
    for p in performances:
        annotatorConstruct = open(filebase + "metamusak/constructors/annotator.ttl", "r")
        perfid = p["uid"]
        perfuri = rdfbase + perfid
        sidecartFile = open(filebase + "performance/" + perfid + "/annotator/annotator.rdf", "w")
        anno = annotatorConstruct.read()
        anno = anno.format(
                Agent5=uri(p["annotatorID"]),
                MasterTimeLine = uri(p["performanceID"] + "/timelines/master"),
                annotatorActivityTimeLine = uri(p["performanceID"] + "/timelines/annotatorActivity"),
                annotatorTimeLineMapAnnotatorAudio = uri(p["performanceID"] + "/timelines/annotatorMapAnnotatorAudio"),
                annotatorTimeLineMapAnnotatorVideo = uri(p["performanceID"] + "/timelines/annotatorMapAnnotatorVideo"),
                annotatorTimeLineMapFreehandAnnotationLayer1 = uri(p["performanceID"] + "/timelines/annotatorTimeLineMapFreehandAnnotationLayer1"),
                annotatorTimeLineMapFreehandAnnotationVideo = uri(p["performanceID"] + "/timeline/annotatorTimeLineMapFreehandAnnotationVideo")
        )
        sidecart = g.query(anno)
        sidecartFile.write(sidecart.serialize(format="turtle"))
        sidecartFile.close()
        annotatorConstruct.close()

def generatePerformance(g, performances, filebase, rdfbase):
    for p in performances:
        performanceConstruct = open(filebase + "metamusak/constructors/performance.ttl", "r")
        perfid = p["uid"]
        perfuri = rdfbase + perfid
        sidecartFile = open(filebase + "performance/" + perfid + "/performance.rdf", "w")
        perf = performanceConstruct.read()
        perf = perf.format(
                performance=uri(p["performanceID"]),
                MasterTimeLine = uri(p["performanceID"] + "/timelines/master"),
                performanceTimeLineMapMMRE = uri(p["performanceID"] + "/timelines/performanceMapMMRE"),
                performanceTimeLineMapPerformanceAudio = uri(p["performanceID"] + "/timelines/performanceMapPerformanceAudio")
        )
        sidecart = g.query(perf)
        sidecartFile.write(sidecart.serialize(format="turtle"))
        sidecartFile.close()
        performanceConstruct.close()

def generatePerformanceAudio(g, performances, filebase, rdfbase):
    for p in performances:
        sourcedir =  filebase + "performance/" + p["uid"] + "/musicalmanifestation/"
        perfid = p["uid"]
        perfuri = rdfbase + perfid
        for audiofname in os.listdir(sourcedir):
            if audiofname.endswith(".mp3"):
                performanceAudioConstruct = open(filebase + "metamusak/constructors/performanceAudio.ttl", "r")
                audiofbase = os.path.splitext(audiofname)[0]
                # found some annotator audio)!
                sidecartFile = open(sourcedir + "/" + audiofbase + ".rdf", "w")
                perfA = performanceAudioConstruct.read()
                perfA = perfA.format(
                        performanceAudio = uri(perfuri + "/musicalmanifestation/" +audiofbase)
                )
                sidecart = g.query(perfA)
                sidecartFile.write(sidecart.serialize(format="turtle"))
                sidecartFile.close()
                performanceAudioConstruct.close()
        
def generateScore(g, performances, filebase, rdfbase):
    for p in performances:
        perfid = p["uid"]
        perfuri = rdfbase + perfid
        sourcedir = filebase + "performance/" + perfid + "/musicalmanifestation/score"
        for page in os.listdir(sourcedir):
            if page.endswith(".jpg"):  # only jpg files - TODO make this accept other conceivable suffixes, e.g. JPG, jpeg, JPEG, png? etc
                pagebase = os.path.splitext(page)[0]
                m = re.match("\w+-(\d+).jpg", page)
                pagenum = int(m.group(1))
                scoreConstruct = open(filebase + "metamusak/constructors/score.ttl", "r")
                scoreSidecartFile = open(filebase + "performance/" + perfid + "/musicalmanifestation/score/"+pagebase+".rdf", "w")
                sc = scoreConstruct.read()
                sc = sc.format(
                    pageOfScore = uri(perfuri + "/musicalmanifestation/score/" + urllib.quote(pagebase))
                )
                scoreSidecart = g.query(sc)
                scoreSidecartFile.write(scoreSidecart.serialize(format="turtle"))
                scoreConstruct.close()
                scoreSidecartFile.close()

                performancePageturnConstruct = open(filebase + "metamusak/constructors/performancePageturn.ttl")
                performancePageturnSidecartFile = open(filebase + "performance/" + perfid + "/musicalmanifestation/pageturn/"+pagebase+".rdf", "w")
                pt = performancePageturnConstruct.read()
                pt = pt.format(
                    MusicalManifestationRealizationEvent = uri(perfuri + "/musicalmanifestation/pageturn/" + str(pagenum)) 
                )
                performancePageturnSidecart = g.query(pt)
                performancePageturnSidecartFile.write(performancePageturnSidecart.serialize(format="turtle"))
                performancePageturnSidecartFile.close()
                performancePageturnConstruct.close()
                score1sourcedir = filebase + "performance/" + perfid + "/musicalmanifestation/score"

        

def generateAnnotatedScore(g, performances, filebase, rdfbase):
    for p in performances:
        perfid = p["uid"]
        perfuri = rdfbase + perfid
        score1sourcedir = filebase + "performance/" + perfid + "/annotation/score1"
        score2sourcedir = filebase + "performance/" + perfid + "/annotation/score2"
        freehandsourcedir = filebase + "performance/" + perfid + "/annotation"
        for page in os.listdir(score1sourcedir):
            m = re.match("opera\d_PG \((\d+)\).jpg", page)
            if m:
                basename = os.path.splitext(page)[0]
                pagenum = m.group(1)
                pageOfAnnotatedScoreLayer1Construct = open(filebase + "metamusak/constructors/annotatedScoreLayer1.ttl")
                sc1 = pageOfAnnotatedScoreLayer1Construct.read()
                sc1 = sc1.format(
                    pageOfAnnotatedScoreLayer1 = uri(perfuri + "/annotation/score1/" + urllib.quote(basename))
                )
                pageOfAnnotatedScoreLayer1Sidecart = g.query(sc1)
                pageOfAnnotatedScoreLayer1SidecartFile = open(score1sourcedir + "/" + basename + ".rdf", "w")
                pageOfAnnotatedScoreLayer1SidecartFile.write(pageOfAnnotatedScoreLayer1Sidecart.serialize(format="turtle"))

                pageOfAnnotatedScoreLayer2Construct = open(filebase + "metamusak/constructors/annotatedScoreLayer2.ttl")
                sc2 = pageOfAnnotatedScoreLayer2Construct.read()
                sc2 = sc2.format(
                    # Note - we intentionally send in Layer 1, and then get Layer 2 in the constructor template via prov:wasDerivedFrom
                    pageOfAnnotatedScoreLayer1 = uri(perfuri + "/annotation/score1/" + urllib.quote(basename))
                )
                pageOfAnnotatedScoreLayer2Sidecart = g.query(sc2)
                pageOfAnnotatedScoreLayer2SidecartFile = open(score2sourcedir + "/" + basename + ".rdf", "w")
                pageOfAnnotatedScoreLayer2SidecartFile.write(pageOfAnnotatedScoreLayer2Sidecart.serialize(format="turtle"))
                
                freehandAnnotationLayer1Construct = open(filebase + "metamusak/constructors/freehandAnnotationLayer1.ttl")
                fh1 = freehandAnnotationLayer1Construct.read()
                fh1 = fh1.format(
                    freehandAnnotationLayer1 = uri(perfuri + "/annotation/" + str(pagenum))
                )
                freehandAnnotationLayer1Sidecart = g.query(fh1)
                freehandAnnotationLayer1SidecartFile = open(freehandsourcedir + "/" + str(pagenum) + ".rdf", "w")
                freehandAnnotationLayer1SidecartFile.write(freehandAnnotationLayer1Sidecart.serialize(format="turtle"))




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

# TODO finish freehandAnnotationvideo stuff
#    pencastOffsetsFile = csv.reader(open(ringcycle + "metamusak/pencastToVideo_offsets.csv", "rU"), delimiter=",", quotechar = '"')
#    pencastOffsets = list()
#    pencastOffsetFields = list()
#    for ix, line in enumerate(pencastOffsetsFile):
#        if ix == 0: # header row - populate fields
#            for field in line:
#                pencastOffsetFields.append(field)
#        else:



    offsets = calculateTimelineOffsets(syncTimestamps)
    g = Graph()
    parseScore(g, userinputrows, ringcycle, rdfbase) # score.ttl, performancePageturns.ttl
    parseAnnotatedScore(g, userinputrows, ringcycle, rdfbase) #annotatedScoreLayer1 & 2, freehandAnnotationLayer1
    parseAnnotator(g, userinputrows, ringcycle, rdfbase, offsets) # annotator.ttl
    parsePerformance(g, userinputrows, ringcycle, rdfbase, offsets) # performance.ttl
#    parseAnnotatorAudio(g, userinputrows, ringcycle, rdfbase) #annotatorAudio.ttl
#    parseAnnotatorVideo(g, userinputrows, ringcycle, rdfbase, offsets) #annotatorAudio.ttl
    parsePerformanceAudio(g, userinputrows, ringcycle, rdfbase) # performanceAudio.ttl
#    parseSubstituteAudio(g, userinputrows, ringcycle, rdfbase) # substituteAudio.ttl
##    parseFreehandAnnotationVideo(g, userinputrows, ringcycle, rdfbase) # substituteAudio.ttl
#    print "AFTER PARSING, GRAPH IS: ", g.serialize(format="turtle")
    generateAnnotator(g, userinputrows, ringcycle, rdfbase)
    generatePerformance(g, userinputrows, ringcycle, rdfbase)
    generatePerformanceAudio(g, userinputrows, ringcycle, rdfbase)
    generateScore(g, userinputrows, ringcycle, rdfbase)
    generateAnnotatedScore(g, userinputrows, ringcycle, rdfbase)


