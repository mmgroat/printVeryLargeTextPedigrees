# coding: utf-8

# App: gimmwebservice
# Original Author - Michael Groat
# 5/27/2023

# global imports
# from __future__ import print_function
# import re
import sys
# from urllib.parse import unquote
# import getpass
# import asyncio
import argparse
import io
import os
import time
import traceback
import math
import collections
from datetime import datetime
from flask import Flask
from flask import request
from flask import abort

# local imports
from classes.tree import Fam, Tree
from classes.pedigree import Pedigree
from classes.descendents import Descendents
from classes.individualsheet import IndividualSheet
from classes.gedcom import Gedcom
from classes.masterindex import MasterIndex
from classes.searchgedcom import SearchGedcom
from classes.surnames import Surnames
from classes.log import Log

app = Flask(__name__)
debug = True

time_count = time.time()
print("Parsing Gedcom")
sys.stdout.flush()

parser = argparse.ArgumentParser(
    description="Create webservice from local gedcom file to serve genealogical HTML pages (May 21 2023)",
    add_help=False,
    usage="python -m flask --app gimmwebservice -g <gedcom relative path and file>",
)
parser.add_argument(
    "-e", 
    "--email", 
    metavar="<STR>", 
    type=str, 
    default=False,
    help="Contact Email",
)
try:
    parser.add_argument(
        "-g",
        "--gedcom-input-file",
        metavar="<FILE>",
        type=argparse.FileType("r", encoding="UTF-8-SIG"),
        default=False,
        help="input GEDCOM file [required]",
    )
except TypeError as e:
    sys.stderr.write("Python >= 3.4 is required to run this script\n")
    sys.stderr.write("(see https://docs.python.org/3/whatsnew/3.4.html#argparse)\n")
    if debug:
        print("An exception occurred:", e)
        traceback.print_exc()
    sys.exit(2)

# extract arguments from the command line
try:
    parser.error = parser.exit
    args = parser.parse_args()
except SystemExit as e:
    parser.print_help(file=sys.stderr)
    if debug:
        print("An exception occurred:", e)
        traceback.print_exc()
    sys.exit(2)

# Load GedCom from file in a NonFS tree (doesn't assume FIDs exist)
if not args.gedcom_input_file:
    sys.stderr.write("A GEDCOM file is required to run this webservice\n")
    sys.exit(2)
    
tree = Tree()
ged = Gedcom(args.gedcom_input_file, tree)
tree.lastmodifiedtime = datetime.fromtimestamp(os.path.getmtime(args.gedcom_input_file.name)).strftime('%B %d, %Y %H:%M:%S')
tree.contactemail = args.email
tree.gimmversion = "Version 0.0.2 (<A HREF=\"http://github.com/mmgroat/gimmwebservice\">Program Information</A>)"
fam_counter = 0
print("Copying Gedcom results to tree data structure")
sys.stdout.flush()
tree.indi = ged.indi
# Add parent information (to any GEDCOM (assume non FS))
for person_num in tree.indi:
    if tree.indi[person_num].famc_num:
        fam_num = list(tree.indi[person_num].famc_num)[0] # get perferred family only hence [0] (only for printing pedigrees, we aren't storing tree)
        if fam_num:
            mother, father = (ged.fam[fam_num].husb_num, ged.fam[fam_num].wife_num)
            if mother is not None or father is not None:
                tree.indi[person_num].parents.add((mother,father))
for num in ged.fam:
    husb, wife = (ged.fam[num].husb_num, ged.fam[num].wife_num)
    if (husb, wife) not in tree.fam:
        fam_counter += 1
        tree.fam[(husb, wife)] = Fam(husb, wife, tree, fam_counter)
        tree.fam[(husb, wife)].tree = tree
    tree.fam[(husb, wife)].chil_num |= ged.fam[num].chil_num
    if ged.fam[num].num:
        tree.fam[(husb, wife)].num = ged.fam[num].num
    if ged.fam[num].facts:
        tree.fam[(husb, wife)].facts = ged.fam[num].facts
    if ged.fam[num].notes:
        tree.fam[(husb, wife)].notes = ged.fam[num].notes
    if ged.fam[num].sources:
        tree.fam[(husb, wife)].sources = ged.fam[num].sources
    tree.fam[(husb, wife)].sealing_spouse = ged.fam[num].sealing_spouse
tree.sources = ged.sour
tree.notes = ged.note
# tree.reset_num_no_fid(self)

# Create information for charts, sheets, indexes and search pages
sys.stdout.flush()
pedigrees = Pedigree(tree)
descendents = Descendents(tree)
individualsheets = IndividualSheet(tree)
searchgedcom = SearchGedcom(tree)
logs = Log(tree)

# Since these are more or less static pages - generate a string of each page and just 
# send that on request, don't regenerate the strings for each request 
tree.sorted_individuals = collections.OrderedDict(sorted(tree.indi.items(), key=lambda x:(x[1].name.surname, x[1].name.given)))
# Put sorted_individuals in a list in order to perform faster slicing in render_submaster (index)
tree.sorted_individuals_list = list(tree.sorted_individuals.items())
tree.magicnum = math.ceil(math.sqrt(len(tree.indi)))
print("Creating and rendering Surnames page")
sys.stdout.flush()
surnames = Surnames(tree)
surnamesoutput = surnames.render()
print("Creating and rendering master index page")
sys.stdout.flush()
masterindex = MasterIndex(tree)
masterindexoutput = masterindex.render_master()
print("Creating and rendering sub index pages")
sys.stdout.flush()
subindexoutput = []
for x in range(tree.magicnum):
    sys.stdout.write("\b\b\b\b\b\b\b\b\b\b\b\b\b\b")
    sys.stdout.write(str(x+1) + "/" + str(tree.magicnum))
    sys.stdout.flush()
    output = masterindex.render_submaster(x)
    if len(output) > 0:
        subindexoutput.append(output)
sys.stdout.write("\n")
#TODO: Question - Do we want to remove birth and death information for living individuals here?
# I've had people contact me in the past requesting this info not be posted.
# Perhaps an option for public/private tree viewing?
# if args.public == True:
#    tree = tree.privatize()

#TODO: Do we want to put photos here? How would a photo work in a text pedigree?

print("Finished parsing GEDCOM into memory in %s seconds." % str(round(time.time() - time_count)))
sys.stdout.flush()

####################
# Define Endpoints:
####################

@app.get('/favicon.ico')
def get_iconimage():
    return app.send_static_file('favicon.ico')

@app.get('/images/background')
def get_backgroundimage():
    return app.send_static_file('background.jpg')

@app.get('/individual/<indi_num>')
@app.get('/individual/<indi_num>/')
def get_individual_sheet(indi_num):
   return individualsheets.render(int(indi_num))

@app.get('/individual/<indi_num>/pedigree')
@app.get('/individual/<indi_num>/pedigree/')
def get_pedigree(indi_num):
   maxlevel = request.args.get('maxlevel')
   if maxlevel is None:
       maxlevel = 198 # 200 shows on chart
   else:
       maxlevel = int(maxlevel) - 2
       if maxlevel < -1:
           maxlevel = -1
   return pedigrees.render(int(indi_num), maxlevel)

@app.get('/individual/<indi_num>/descendents')
@app.get('/individual/<indi_num>/descendents/')
def get_descendents(indi_num):
   maxlevel = request.args.get('maxlevel')
   if maxlevel is None:
       maxlevel = 198 # 200 shows on chart
   else:
       maxlevel = int(maxlevel) - 2
       if maxlevel < -1:
           maxlevel = -1
   return descendents.render(int(indi_num), maxlevel)

@app.get('/')
@app.get('/index')
@app.get('/index/')
def get_main_index():
    return masterindexoutput 

@app.get('/index/<index_num>')
@app.get('/index/<index_num>/')
def get_sub_index(index_num):
    try:
        index_num_int = int(index_num)
    except ValueError as e:
        abort(404)
    if ((index_num_int < 0) or (index_num_int > len(subindexoutput) - 1)):
        abort(404) 
    return subindexoutput[int(index_num_int)]

@app.get('/search')
@app.post('/search')
def search_gedcom():
    return searchgedcom.render()

@app.get('/surnames')
def get_surnames():
    return surnamesoutput

# TODO:
@app.get('/logs')
def get_access_log():
    return logs.render()

# TODO:
@app.get('/counters')
def get_counters():
    # TODO: maybe put these at the bottom of all pages?
    return individualsheets.render(1) #testing

# TODO:
@app.get('/guestbook')
def get_guestbook():
    # TODO: Do we want to have a persistent guestbook?
    return individualsheets.render(1) #testing

#@app.get('/extract')
#def get_gedcom():
    # Do we want to download seperate branchs off the underlying GEDCOM? Note, we are going from a 
    # GEDCOM to Memory that's not a 100% translation, then going from that back to GEDCOM. It's 
    # currently not a 100% translation, so do we want to include or get it up to 100%
    # return individualsheets.render(1) #testing

#@app.get('/createlink')
#def put_link():
    # Do we even want to allow links? Seems dangerous nowadays to allow writes to a webstie, unless 
    # it's monitored before it's publish. This could be the start of a wiki tree? How about 
    # adding/changing individuals? (like WikiTree?) Where people could log in and up load their 
    # individiual GEDCOMS, and perhaps everyone merges them into a One-World-Family-Tree. (I know 
    # this already has been done and it would take a team of engineers. For now, I'm focusing on 
    # Genealogy aids to assist with personal research. So focus on -- a GEDCOM to web server that 
    # specializes in fast and efficient collaspable pedigree and descendency charts of greater than 
    # 100k individuals. --)
    # return individualsheets.render(1) #testing

# start the webserver
if __name__ == "__main__":
    app.debug = True
    app.run(host="0.0.0.0")
