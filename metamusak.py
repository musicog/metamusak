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
        performanceAudioSynctime = datetime.strptime(p["performanceAudio"], "%d/%m/%Y %H:%M:%S") #granularity to 1 second
        MMRESynctime = datetime.strptime(p["MMRE"],"%d/%m/%Y %H:%M:%S") #Musical Manifestation Realisation Event Sync Time, granularity to 1 second
        freehandAnnotationLayer1Synctime = datetime.strptime(p["freehandAnnotationLayer1"], "%d/%m/%Y %H:%M:%S.%f") #annotations made on the iPad
        #sourceAnnotatorVideoSynctime = datetime.strptime(p["sourceAnnotatorVideo"]) "%H:%M:%S") #FIXME these details are not in the .csv!!!
        #freehandAnnotationVideo_3_Synctime = datetime.strptime(p["freehandAnnotationVideo"], "%H:%M:%S")
        offsets["basetime"] = performanceAudioSynctime      # we declare performanceAudio to be our ground truth universal timeline # thus, map different temporal offsets between that and the others
        offsets["performanceAudio"] = 0;
     
        if p["annotatorAudio"]: # we only have it for Rheingold
            offsets["annotatorAudio"] = generateTimeDelta(datetime.strptime(p["annotatorAudio"], "%H:%M:%S")) #Digitpen only specific to a minute
            offsets["annotatorAudio"] = offsets["basetime"] - generateTimeDelta(datetime.strptime(p["annotatorAudio"], "%H:%M:%S"))
        else:
            offsets["annotatorAudio"] = "None" #this one says "None" the others are 0

        if p["annotatorVideo"]: 
            # therefore, subtract annotatorVideo syncTimestamp (as timedelta) from basetime to get annotatorVideo time
            # EXCEPT for WALKURE, where we need to add 52seconds 
            perfid = p["uid"]
            if perfid != "gvX3hrDeTEA": #for all except Walkuere
                annotatorVideoSynctime = offsets["basetime"] - generateTimeDelta(datetime.strptime(p["annotatorVideo"], "%H:%M:%S"))
                offsets["annotatorVideo"] = getOffsetSeconds(annotatorVideoSynctime, offsets["basetime"])
            else:
                annotatorVideoSynctime = offsets["basetime"] + generateTimeDelta(datetime.strptime(p["annotatorVideo"], "%H:%M:%S")) #always ADD timeDelta for Walkuere
                offsets["annotatorVideo"] = getOffsetSeconds(annotatorVideoSynctime, offsets["basetime"])
        else:  
            offsets["annotatorVideo"] = 0
                   
        #if p["sourceAnnotatorVideo"] :
         #   sourceAnnotatorVideoSynctime = offsets["basetime"] - generateTimeDelta(datetime.strptime(p["sourceAnnotatorVideo"], "%H:%M:%S"))
          #  offsets["sourceAnnotatorVideo"] = getOffsetSeconds(sourceAnnotatorVideoSynctime, offsets ["basetime"])
        #else:
          #  offsets["sourceAnnotatorVideo"] = 0

        if p["freehandAnnotationLayer1"] :
            freehandAnnotationLayer1 = offsets["basetime"] - generateTimeDelta(datetime.strptime(p["freehandAnnotationLayer1"], "%d/%m/%Y %H:%M:%S.%f")) # fhAL1St also has microseconds..."%d/%m/%Y %H:%M:%S.%f"
            offsets["freehandAnnotationLayer1"] = getOffsetSeconds(freehandAnnotationLayer1Synctime, offsets["basetime"]) 
        else:
            offsets["freehandAnnotationLayer1"] = 0
        
        if "freehandAnnotationVideo" in p: #FIXME 
            freehandAnnotationVideo_1_Synctime = offsets["basetime"] - generateTimeDelta(datetime.strptime(p["annotatorVideo"], "%H:%M:%S"))
            freehandAnnotationVideo_2_Synctime = freehandAnnotationVideo_1_Synctime + pencastTimestamps
            freehandAnnotationVideo_3_Synctime = freehandAnnotationVideo_2_Synctime - writingStarttime
            offsets["freehandAnnotationVideo"] = getOffsetSeconds(freehandAnnotationVideo_3_Synctime, offsets["basetime"])
        else:
            offsets["freehandAnnotationVideo"] = 0
        
        if p["MMRE"]:
            MMRESynctime = offsets["basetime"] - generateTimeDelta(datetime.strptime(p["MMRE"], "%d/%m/%Y %H:%M:%S"))
            offsets["MMRE"] = getOffsetSeconds(MMRESynctime, offsets["basetime"])
        else:
            offsets["MMRE"] = 0
            
        performanceOffsets[offsets["perfid"]] = offsets
    return performanceOffsets

#####################################

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
        perfuri = rdfbase + perfid # URI of the "root" of THIS performance
        # set up the source directory for the score pages
        sourcedir = filebase + "performance/" + perfid + "/musicalmanifestation/score"
        # read in performance page turns
        # note regarding the CSV files produced by Richard's tool:
        # * The last page before the end of an act is NOT encoded in the same way as the others
        #   instead its turn time is encoded as an act ending event (e.g. "act 1 ends")
        # * also, act starts and ends are encoded to the second, whereas all other pageturns are
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
                    if m: # note -- m is a complex object representing the outcome of the regex match, not just the \d+ captured
                        thisPage["pageNum"] =  int(m.group(1)) # m.group(1) is the \d+ that was captured, but by default its as a string, so we use int() to turn it into a number
                    else: 
                        thisPage["pageNum"] = prevPage+1 
                    thisPage["opera"] = line[1]
                    thisPage["act"] = line[2]
                    try:
                        # strptime takes a string that looks like a timestamp and turns it into a "real" time object -- look it up ;)
                        thisPage["turntime"] = datetime.strptime(line[4], "%Y-%m-%d %H:%M:%S.%f")
                    except:
                    #TODO for Richard: tool specifies pageturns to millisecond but act starts/ends to the second -  except for the final pages in Walkure, which he recreated by listening to the audio again, which are also to the second.
                        thisPage["turntime"] = datetime.strptime(line[4], "%Y-%m-%d %H:%M:%S")
                    # each page is preceded in the file by a timestamped event of some sort...
                    # even the first page, as there is other timestamped info in the file (e.g. start of act)
                    # we can rely on this when calculating MMRE durations
                    thisPage["starttime"] = prevTime
                    thisPage["duration"] = thisPage["turntime"] - thisPage["starttime"]  # i.e. page end minus page start = page duration
                    pageturns[thisPage["pageNum"]] = thisPage 
                    prevPage = thisPage["pageNum"] # track for when we reach an act ends event 
                # regardless of event type, record the timestamp for MMRE duration calculation
                try: 
                    prevTime = datetime.strptime(line[4], "%Y-%m-%d %H:%M:%S.%f")
                except: 
                    prevTime = datetime.strptime(line[4], "%Y-%m-%d %H:%M:%S")

        # now work through the page image files
        for page in os.listdir(sourcedir):
            if page.endswith(".pdf"):  # only pdf files - TODO make this accept other conceivable suffixes, e.g. JPG, jpeg, JPEG, png? etc
                    #print sourcedir + "/" + page
                    m = re.search("(\w+)_originalscore_page(\d+).pdf", page)
                    pagenum = int(m.group(2))
                    if pagenum in pageturns:
                    # set up score.ttl
                        scoreTemplate = open(filebase + "metamusak/templates/score.ttl", "r")
                        sc = scoreTemplate.read()
                        sc = sc.format(
                            conceptScore = uri(perfuri + "/musicalmanifestation/conceptScore"),
                            score = uri(perfuri + "/musicalmanifestation/score"),
                            pageOfScore = uri(perfuri + "/musicalmanifestation/score/" + urllib.quote(os.path.splitext(page)[0])),
                            MusicalManifestationRealizationEvent = uri(perfuri + "/musicalmanifestation/pageturn/" + str(pagenum)) 
                        )
                    # set up performancePageturn.ttl 
                        performancePageturnTemplate = open(filebase + "metamusak/templates/performancePageturn.ttl")
                        pt = performancePageturnTemplate.read()
                        pt = pt.format(
                            MusicalManifestationRealizationEvent = uri(perfuri + "/musicalmanifestation/pageturn/" + str(pagenum)), 
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
                        Agent5 = uri(p["annotatorID"]),
                        performance = uri(perfuri),
                        annotatedScoreLayer1 = uri(perfuri + "/annotation/score1/" + urllib.quote(basename)),
                        annotatedScoreLayer2 = uri(perfuri + "/annotation/score2/" + urllib.quote(sc2basename)),
                        annotatorVideo = uri(perfuri + "/annotator/annotator1.mov"), # FIXME address other videos
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
                digitalSignal = "",
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
                freehandAnnotationVideoTimeLine = uri(p["performanceID"] + "/timelines/freehandAnnotationVideo"),
                freehandAnnotationLayer1TimeLine = uri(p["performanceID"] + "/timelines/freehandAnnotationLayer1")
        )
        
        g.parse(data=anno, format="turtle")
        annotatorTemplate.close()


def parsePerformanceAudio(g, performances, filebase, rdfbase, offsets):                
    performanceAudioTemplate = open(filebase + "metamusak/templates/performanceAudio.ttl", "r")
    perfau = performanceAudioTemplate.read()
    for p in performances:
        sourcedir =  filebase + "performance/" + p["uid"] + "/musicalmanifestation/"
        perfuri = rdfbase + p["uid"]
        for audiofname in os.listdir(sourcedir):
            if audiofname.endswith(".mp3"):
                # found some annotator audio!
                #print sourcedir + audiofname....debugging, oooh yeah.
                ##timestamp = open(os.path.splitext(audiofname)[0] + ".txt").read().rstrip()
                mediainfo = getMediaInfo(sourcedir + audiofname)
                query = perfau.format(
                        performance = uri(perfuri),
                        performanceAudio = uri(perfuri + "/musicalmanifestation/" + urllib.quote(os.path.splitext(audiofname)[0])), # cut off the ".mp3" suffix
                        digitalSignal = uri(perfuri + "/musicalmanifestation/" + urllib.quote(audiofname)),
                        digitalSignalIntervalStart = lit(offsets[p["uid"]]["performanceAudio"]),
                        ##digitalSignalIntervalStart = lit(timestamp),
                        digitalSignalIntervalDuration = lit(mediainfo["duration"]),
                        performanceAudioTimeLine = uri(perfuri + "/timelines/performanceAudio"),
                        performanceTimeLine = uri(perfuri + "/timelines/performanceTimeLine"),
                        substituteAudio = uri(perfuri + "/musicalmanifestation/" + urllib.quote(os.path.splitext(audiofname)[0]) + "_sub") #TODO replace with actual substitute audio 
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
                        substituteAudio = uri(perfuri + "/musicalmanifestation/" + urllib.quote(os.path.splitext(audiofname)[0]) + "sub") #TODO replace with actual substitute audio
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
    annotatorVideoTemplate = open(filebase + "metamusak/templates/annotatorVideo.ttl", "r")
    anno = annotatorVideoTemplate.read()
    for p in performances:
        sourcedir =  filebase + "performance/" + p["uid"] + "/annotator/"
        perfuri = rdfbase + p["uid"]
        for videofname in os.listdir(sourcedir):
            if videofname.endswith(".mov"): #TODO enable other formats e.g. .mov, .mp4, etc AND MOVE .MP4s BACK INTO THAT FOLDER!!!
                # found some annotator video!
                mediainfo = getMediaInfo(sourcedir + videofname)
                for key in mediainfo:
                    if mediainfo[key] is None:
                        continue # skip non-values
                query = anno.format(
                        performance = uri(perfuri),
                        Agent5 = uri(p["annotatorID"]),
                        annotatorVideo = uri(perfuri + "/annotator/" + urllib.quote(os.path.splitext(videofname)[0])), # cut off the file suffix
                        annotatorVideoIntervalStart = lit(offsets[p["uid"]]["annotatorVideo"]),# FIXME NOT THE CORRECT DATE
                        annotatorVideoIntervalDuration = lit(mediainfo["duration"]),
                        annotatorActivityTimeLine = uri(perfuri + "/timelines/annotatorActivity"),
                        annotatorVideoTimeLine = uri(perfuri + "/timelines/annotatorVideo"),
                    )
                g.parse(data=query, format="turtle")

def parseSourceAnnotatorVideo(g, performances, filebase, rdfbase, offsets):
    sourceAnnotatorVideoTemplate = open(filebase + "metamusak/templates/sourceAnnotatorVideo.ttl", "r")
    anno = sourceAnnotatorVideoTemplate.read()
    for p in performances:
        sourcedir =  filebase + "performance/" + p["uid"] + "/annotator/sourceAnnotatorVideo/"
        perfuri = rdfbase + p["uid"]
        for videofname in os.listdir(sourcedir):
            if videofname.endswith(".MTS"): #TODO enable other formats e.g. .mov, .mp4, etc 
                # found some sourceAnnotatorVideo!
                mediainfo = getMediaInfo(sourcedir + videofname)
                for key in mediainfo:
                    if mediainfo[key] is None:
                        continue # skip non-values
                query = anno.format(
                        performance = uri(perfuri),
                        Agent5 = uri(p["annotatorID"]),
                        sourceAnnotatorVideo = uri(perfuri + "/annotator/sourceAnnotatorVideo/" + urllib.quote(os.path.splitext(videofname)[0])), # cut off the file suffix 
                        sourceAnnotatorVideoIntervalStart = lit(mediainfo["date"]), 
                        sourceAnnotatorVideoIntervalDuration = lit(mediainfo["duration"]),
                        annotatorActivityTimeLine = uri(perfuri + "/timelines/annotatorActivity"),
                        sourceAnnotatorVideoTimeLine = uri(perfuri + "/timelines/sourceAnnotatorVideo"),
                    )
                g.parse(data=query, format="turtle")


def parseFreehandAnnotationVideo (g, performances, filebase, rdfbase, offsets):
    freehandAnnotationVideoTemplate = open(filebase + "/metamusak/templates/freehandAnnotationVideo.ttl", "r")
    anno = freehandAnnotationVideoTemplate.read()
    for p in performances:
        sourcedir = filebase + "performance/" + p["uid"] + "/annotation" + "/freehandAnnotationVideo/"
        perfuri = rdfbase + p["uid"]
        for videofname in os.listdir(sourcedir):
            if videofname.endswith(".mp4"):
                mediainfo = getMediaInfo(sourcedir + videofname)
                for key in mediainfo: 
                    #print key + " : " + mediainfo[key]
                    if mediainfo[key] is None:
                        continue
                query = anno.format(
                        performance = uri(perfuri),
                        Agent5 = uri(p["annotatorID"]),
                        freehandAnnotationVideo = uri(perfuri + "/annotation" + "/freehandAnnotationVideo/" + urllib.quote(os.path.splitext(videofname)[0])),
                        freehandAnnotationVideoBody = uri(perfuri + "/annotation" + "/freehandAnnotationVideo/" + urllib.quote(videofname)),
                        freehandAnnotationVideoBodyIntervalStart = lit(mediainfo["date"]),
                        freehandAnnotationVideoBodyIntervalDuration = lit(mediainfo["duration"]),
                        annotatorActivityTimeLine = uri(perfuri + "/timelines/annotatorActivity"),
                        freehandAnnotationVideoTimeLine = uri(perfuri + "/timelines/freehandAnnotationVideo"),
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
            thisfile["duration"] = str(float(track.duration) * .001)
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
    #userinputfile = csv.reader(open(filebase + "metamusak/" + perfid + "user_input.csv", "r"), delimiter=",", quotechar='"')
    #for ix, line in enumerate(pageturnsfile):
    #        if ix <= 1: # skip header
    #            next
    #        else: # content row - use the content from here
    #            if userinputname != uri:
    #                personidentifier = dict()
    #                   personidentifier["id"] = 
    #                   personidentifier["label"] = str()
    #           else:
    
    
                    # take the human written label, 
                    # replace it with a URI by using the uid()
                    # keep names as labels i.e. add ' rdfs:label " " '
                    #doforall (annotator, listener, arranger, etc)
                        #TODO in the future when we work on the web interface: do something useful
                        # take content put into the .csv file
                        #if it's a URI already, run with it,
                        # if not, take the name, and hash it into a URI
                        # disambiguate between people? Optionally for now, possibly just do this in the Web UI
    return thisPerformance 
              
def generateAnnotator(g, performances, filebase, rdfbase):
    for p in performances:
        annotatorConstruct = open(filebase + "metamusak/constructors/annotator.ttl", "r")
        perfid = p["uid"]
        perfuri = rdfbase + perfid
        sidecartFile = open(filebase + "performance/" + perfid + "/annotator/annotator.ttl", "w")
        anno = annotatorConstruct.read()
        anno = anno.format(
                Agent5=uri(p["annotatorID"]),
                MasterTimeLine = uri(p["performanceID"] + "/timelines/master"),
                annotatorAudioTimeLine = uri(p["performanceID"] + "/timelines/annotatorAudio"),
                annotatorVideoTimeLine = uri(p["performanceID"] + "/timelines/annotatorVideo"),
                annotatorActivityTimeLine = uri(p["performanceID"] + "/timelines/annotatorActivity"),
                freehandAnnotationLayer1TimeLine = uri(p["performanceID"] + "/timelines/freehandAnnotationLayer1"),
                annotatorTimeLineMapAnnotatorAudio = uri(p["performanceID"] + "/timelines/annotatorMapAnnotatorAudio"),
                annotatorTimeLineMapAnnotatorVideo = uri(p["performanceID"] + "/timelines/annotatorMapAnnotatorVideo"),
                annotatorTimeLineMapFreehandAnnotationLayer1 = uri(p["performanceID"] + "/timelines/annotatorTimeLineMapFreehandAnnotationLayer1"),
                annotatorTimeLineMapFreehandAnnotationVideo = uri(p["performanceID"] + "/timeline/annotatorTimeLineMapFreehandAnnotationVideo"),
                freehandAnnotationVideoTimeLine = uri(p["performanceID"] + "/timelines/freehandAnnotationVideo"),

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
        sidecartFile = open(filebase + "performance/" + perfid + "/performance.ttl", "w")
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
                sidecartFile = open(sourcedir + "/" + audiofbase + ".ttl", "w")
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
            if page.endswith(".pdf"):  # only pdf files - TODO make this accept other conceivable suffixes, e.g. JPG, jpeg, JPEG, png? etc
                pagebase = os.path.splitext(page)[0]
                m = re.search("(\w+)_originalscore_page(\d+).pdf", page)
                pagenum = int(m.group(2))
                scoreConstruct = open(filebase + "metamusak/constructors/score.ttl", "r")
                scoreSidecartFile = open(filebase + "performance/" + perfid + "/musicalmanifestation/score/" + pagebase + ".ttl", "w")
                sc = scoreConstruct.read()
                sc = sc.format(
                    pageOfScore = uri(perfuri + "/musicalmanifestation/score/" + urllib.quote(pagebase))
                )
                scoreSidecart = g.query(sc)
                scoreSidecartFile.write(scoreSidecart.serialize(format="turtle"))
                scoreConstruct.close()
                scoreSidecartFile.close()
                
                performancePageturnConstruct = open(filebase + "metamusak/constructors/performancePageturn.ttl", "r")
                performancePageturnSidecartFile = open(filebase + "performance/" + perfid + "/musicalmanifestation/pageturn/" + pagebase + ".ttl", "w")
                pt = performancePageturnConstruct.read()
                #HACK: the listener's page numbers are 1 below the annotator's page numbers, EXCEPT IN WALKUERE, where they are the same
                #i.e. the listener's page 3 is the annotator's page 4 (both refer to the same page of score, which has yet another page number)
                adjustedPageNum = pagenum
                if perfid != "gvX3hrDeTEA": #for all except Walkuere
                    adjustedPageNum = adjustedPageNum - 1
                pt = pt.format(
                        MusicalManifestationRealizationEvent = uri(perfuri + "/musicalmanifestation/pageturn/" + str(adjustedPageNum))
                )
                performancePageturnSidecart = g.query(pt)
                performancePageturnSidecartFile.write(performancePageturnSidecart.serialize(format="turtle"))
                performancePageturnSidecartFile.close()
                performancePageturnConstruct.close()
                        
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
                pageOfAnnotatedScoreLayer1SidecartFile = open(score1sourcedir + "/" + basename + ".ttl", "w")
                pageOfAnnotatedScoreLayer1SidecartFile.write(pageOfAnnotatedScoreLayer1Sidecart.serialize(format="turtle"))

                pageOfAnnotatedScoreLayer2Construct = open(filebase + "metamusak/constructors/annotatedScoreLayer2.ttl")
                sc2 = pageOfAnnotatedScoreLayer2Construct.read()
                sc2 = sc2.format(
                    # Note - we intentionally send in Layer 1, and then get Layer 2 in the constructor template via prov:wasDerivedFrom
                    pageOfAnnotatedScoreLayer1 = uri(perfuri + "/annotation/score1/" + urllib.quote(basename))
                )
                pageOfAnnotatedScoreLayer2Sidecart = g.query(sc2)
                pageOfAnnotatedScoreLayer2SidecartFile = open(score2sourcedir + "/" + basename + ".ttl", "w")
                pageOfAnnotatedScoreLayer2SidecartFile.write(pageOfAnnotatedScoreLayer2Sidecart.serialize(format="turtle"))
                
                freehandAnnotationLayer1Construct = open(filebase + "metamusak/constructors/freehandAnnotationLayer1.ttl")
                fh1 = freehandAnnotationLayer1Construct.read()
                fh1 = fh1.format(
                    freehandAnnotationLayer1 = uri(perfuri + "/annotation/" + str(pagenum))
                )
                freehandAnnotationLayer1Sidecart = g.query(fh1)
                freehandAnnotationLayer1SidecartFile = open(freehandsourcedir + "/" + str(pagenum) + ".ttl", "w")
                freehandAnnotationLayer1SidecartFile.write(freehandAnnotationLayer1Sidecart.serialize(format="turtle"))
                
def generateAnnotatorVideo(g, performances, filebase, rdfbase):
    for p in performances:
        perfid = p["uid"]
        perfuri = rdfbase + perfid
        sourcedir = filebase + "performance/" + perfid + "/annotator/"
        for videofname in os.listdir(sourcedir):
                if videofname.endswith(".mov"):
                    basename = urllib.quote(os.path.splitext(videofname)[0])
                    sidecartFile = open(filebase + "performance/" + perfid + "/annotator/" + basename + ".ttl", "w")
                    annotatorVideoConstruct = open(filebase + "metamusak/constructors/annotatorVideo.ttl")
                    anno = annotatorVideoConstruct.read()
                    anno = anno.format(
                            annotatorVideo = uri(perfuri + "/annotator/" + basename)
                    )
                    sidecart = g.query(anno)
                    sidecartFile.write(sidecart.serialize(format="turtle"))
                    sidecartFile.close()
                    annotatorVideoConstruct.close()

def generateSourceAnnotatorVideo(g, performances, filebase, rdfbase, offsets):
    for p in performances:
        perfid = p["uid"]
        perfuri = rdfbase + perfid
        sourcedir = filebase + "performance/" + perfid + "/annotator/sourceAnnotatorVideo/"
        for videofname in os.listdir(sourcedir):
                if videofname.endswith(".MTS"):
                    basename = urllib.quote(os.path.splitext(videofname)[0])
                    sidecartFile = open(filebase + "performance/" + perfid + "/annotator/sourceAnnotatorVideo/" + basename + ".ttl", "w") 
                    sourceAnnotatorVideoConstruct = open(filebase + "metamusak/constructors/sourceAnnotatorVideo.ttl")
                    anno = sourceAnnotatorVideoConstruct.read()
                    anno = anno.format(
                            sourceAnnotatorVideo = uri(perfuri + "/annotator/sourceAnnotatorVideo/" + basename)
                    )
                    sidecart = g.query(anno)
                    sidecartFile.write(sidecart.serialize(format="turtle"))
                    sidecartFile.close()
                    sourceAnnotatorVideoConstruct.close()

def generateAnnotatorAudio(g, performances, filebase, rdfbase):
        for p in performances:
            perfid = p["uid"]
            perfuri = rdfbase + perfid
            sourcedir = filebase + "performance/" + perfid + "/annotation/audio/"
            for audiofname in os.listdir(sourcedir):
                if audiofname.endswith(".m4a"):
                    basename = urllib.quote(os.path.splitext(audiofname)[0])
                    sidecartFile = open(filebase + "performance/" + perfid + "/annotation/audio/" + basename + ".ttl", "w")
                    annotatorAudioConstruct = open(filebase + "metamusak/constructors/annotatorAudio.ttl")
                    anno = annotatorAudioConstruct.read()
                    anno = anno.format(
                            annotatorAudio = uri(perfuri + "/annotation/audio/" + basename)
                    )
                    sidecart = g.query(anno)
                    sidecartFile.write(sidecart.serialize(format="turtle"))
                    sidecartFile.close()
                    annotatorAudioConstruct.close()


def generateFreehandAnnotationVideo (g, performances, filebase, rdfbase, offsets):
    for p in performances:
        perfid = p["uid"]
        perfuri = rdfbase + p["uid"]
        sourcedir = filebase + "performance/" + perfid + "/annotation" + "/freehandAnnotationVideo/"
        for videofname in os.listdir(sourcedir):
            if videofname.endswith(".mp4"):
                    freehandAnnotationVideoConstruct = open(filebase + "metamusak/constructors/freehandAnnotationVideo.ttl", "r")
                    basename = urllib.quote(os.path.splitext(videofname)[0])
                    sidecartFile = open(filebase + "performance/" + perfid + "/annotation" + "/freehandAnnotationVideo/" + basename + ".ttl", "w")
                    anno = freehandAnnotationVideoConstruct.read()
                    anno = anno.format(
                           # performance = uri(perfuri),
                            #Agent5 = uri(p["annotatorID"]),
                            freehandAnnotationVideo = uri(perfuri + "/annotation" + "/freehandAnnotationVideo/" + urllib.quote(os.path.splitext(videofname)[0]))
                           # freehandAnnotationVideoBody = uri(perfuri + "/annotation" + "/freehandAnnotationVideo/" + urllib.quote(videofname)),
                            #freehandAnnotationVideoBodyIntervalStart = lit(mediainfo["date"]),
                            #freehandAnnotationVideoBodyIntervalDuration = lit(mediainfo["duration"]),
                            #annotatorActivityTimeLine = uri(perfuri + "/timelines/annotatorActivity"),
                            #freehandAnnotationVideoTimeLine = uri(perfuri + "/timelines/freehandAnnotationVideo"),
                    )
                    sidecart = g.query(anno)
                    sidecartFile.write(sidecart.serialize(format="turtle"))
                    sidecartFile.close()
                    freehandAnnotationVideoConstruct.close()
  

if __name__ == "__main__": 
    # Set up physical paths, i.e. where things live on the hard drive
    ringcycle = "/Volumes/Terhin_oma_eksternali/MetaRingCycle/" # top level directory that contains the metamusak and performance folders
    perfbase = ringcycle + "performance/" # the performance folder
    # rdf path, i.e. the prefix of every URI generated
    rdfbase = "http://performance.data.t-mus.org/performance/" 

############INPUT READING - currently from CSV, in future from web interface################################

    # Read in the user's input - currently from CSV files in the metamusak folder; in future, from a web interface
    userinputfile = csv.reader(open(ringcycle + "metamusak/user_input.csv", "rU"), delimiter = ",", quotechar = '"')
    userinputrows = list() # will contain all the content, i.e. all the dictionaries holding key:value pairs for each opera
    userinputfields = list() # will contain all the column headers
    for ix, line in enumerate(userinputfile):
        if ix == 0: # header row - populate fields (i.e. column headers in CSV)
            for field in line:
                userinputfields.append(field)
        else : # content row: fill in fields for this performance
            thisPerformance = dict() # will hold key:value pairs, where keys are column headers and values are the content
            for ix, field in enumerate(userinputfields):
                thisPerformance[field] = line[ix]
            # mint any URIs not provided by the user... TODO in the future, currently does nothing
            thisPerformance = mintRequiredURIs(thisPerformance)
            userinputrows.append(thisPerformance)
    for p in userinputrows: # for each dictionary representing a performance's key : value pairs
        # determine the UID for this performance, i.e. the <UID> in  /performance/<UID>
        p["uid"] = p["performanceID"][p["performanceID"].rindex("/")+1:]

    # Read in the offset data - currently from CSV files in the metamusak folder; in future, from a web interface
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

# TODO finish freehandAnnotationVideo stuff
    pencastOffsetsFile = csv.reader(open(ringcycle + "metamusak/pencastToVideo_offsets.csv", "rU"), delimiter=",", quotechar = '"')
    pencastOffsets = list()
    pencastOffsetFields = list()
    for ix, line in enumerate(pencastOffsetsFile):
        if ix == 0: # header row - populate fields
            for field in line:
                pencastOffsetFields.append(field)
        else: #content row -- fill in fields for this ...?
            pencastTimestamps = dict()
            for ix, field in enumerate(pencastOffsetFields):
                pencastTimestamps[field] = line[ix]
            pencastOffsets.append(pencastTimestamps)

#a) start time of each file (according to pen clock)
#b) delay between start of file and start of writing

#So offset calculation goes: (for each freehandAnnotationVideo) 
#Take (pre-calculated) offset between performance time and annotator video time --> annotatorVideo offset
#Adjust by a) above
#From this time, subtract b) above
#Use this to calculate offset between performance time and a) above


############ NOW FINISHED READING INPUT ###############################################

    offsets = calculateTimelineOffsets(syncTimestamps) # figure out the timeline offset logic
    g = Graph() # create the grandmaster graph

############ START PARSING, i.e. filling templates and reading into graph #############
    parseScore(g, userinputrows, ringcycle, rdfbase) # score.ttl, performancePageturns.ttl
    parseAnnotatedScore(g, userinputrows, ringcycle, rdfbase) #annotatedScoreLayer1 & 2, freehandAnnotationLayer1
    parseAnnotator(g, userinputrows, ringcycle, rdfbase, offsets) # annotator.ttl
    parsePerformance(g, userinputrows, ringcycle, rdfbase, offsets) # performance.ttl
    parseAnnotatorAudio(g, userinputrows, ringcycle, rdfbase) #annotatorAudio.ttl
    parseAnnotatorVideo(g, userinputrows, ringcycle, rdfbase, offsets) #annotatorAudio.ttl
    parsePerformanceAudio(g, userinputrows, ringcycle, rdfbase, offsets) # performanceAudio.ttl
    parseSubstituteAudio(g, userinputrows, ringcycle, rdfbase) # substituteAudio.ttl
    parseFreehandAnnotationVideo(g, userinputrows, ringcycle, rdfbase, offsets) # substituteAudio.ttl
    parseSourceAnnotatorVideo(g, userinputrows, ringcycle, rdfbase, offsets)
    #parseTimelines #timelines.ttl
#    print "AFTER PARSING, GRAPH IS: ", g.serialize(format="turtle")

############ FINISHED PARSING, now construct the sidecart turtle and write into files #
    generateAnnotator(g, userinputrows, ringcycle, rdfbase)
    generatePerformance(g, userinputrows, ringcycle, rdfbase)
    generatePerformanceAudio(g, userinputrows, ringcycle, rdfbase)
    generateScore(g, userinputrows, ringcycle, rdfbase)
    generateAnnotatedScore(g, userinputrows, ringcycle, rdfbase)
    generateAnnotatorVideo(g, userinputrows, ringcycle, rdfbase)
    generateAnnotatorAudio(g, userinputrows, ringcycle, rdfbase)
    generateFreehandAnnotationVideo(g, userinputrows, ringcycle, rdfbase, offsets)
    generateSourceAnnotatorVideo(g, userinputrows, ringcycle, rdfbase, offsets)
    #generateTimelines #timelines.ttl

