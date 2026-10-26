Documentation of IGRA v2.2 Station History Information

Last updated: 19 January 2023

---------------------
Notes:
---------------------

1. This readme file is formatted for viewing in a text editor such as Windows Notepad or similar Linux-based editor.

2. The below information applies to station history information in versions 2.0 to 2.2 of IGRA.

------------------------------------------------------------------------
TABLE OF CONTENTS
------------------------------------------------------------------------

I. QUICK START
II. FORMAT OF METADATA RECORDS
III. Version History
IV. Background

------------------------------------------------------------------------
I. QUICK START
------------------------------------------------------------------------

Start by downloading "igra2-metadata.txt", which has station history 
information for all stations in IGRA for which such information is 
available.  You can find this filein the directory /pub/data/igra/v2 at
ftp.ncdc.noaa.gov or pointing your browser to
http://www1.ncdc.noaa.gov/pub/data/igra/v2.  Then, to manually locate the 
history information for a specific station, proceed as follows:

- Open "igrav2.2-metadata.txt" with your favorite text editor and adjust the 
  window size to accommodate the rather long lines in the file.

- Scroll or search through the file to find the station's identification 
  number or name (e.g., USM00072201 or Key West).  Note that station records 
  are indexed by the station identifier used in IGRA (columns 
  1-11) which often contains the most recent World Meteorological Organization 
  (WMO) identification number for a particular location (e.g., 71600 for 
  Sable Island).  Original WMO identification numbers are provided in 
  columns 7-11 (e.g., 72600 for pre-1977 records at Sable Island).

- Look at the date and event type fields to identify the station history 
  information you are interested in.  Alternatively, to read the metadata 
  file with a computer program, refer to the section in this description 
  file that defines the metadata fields and identify the fields of 
  interest.

------------------------------------------------------------------------
II. FORMAT OF METADATA RECORDS
------------------------------------------------------------------------

Each Record in the "igrav2.2-metadata.txt" file contains information for one 
"event" as identified by the station identification number, date, and 
event type.  Event types are either dynamic (i.e., reporting a change) or 
static (i.e., reporting a practice or equipment in use at the time of the 
event date).  The format of the fields is described below.

Variable   Columns     Type
------------------------------
IGRAID         1- 11   Character
WMOID         13- 17   Integer
NAME          19- 48   Character
NAMFLAG       50- 50   Character
LATITUDE      52- 60   Real
LATFLAG       62- 62   Character
LONGITUDE     64- 72   Real
LONFLAG       74- 74   Character
ELEVATION     76- 81   Real
ELVFLAG       83- 83   Character
YEAR          85- 88   Integer
MONTH         90- 91   Integer
DAY           93- 94   Integer
HOUR          96- 97   Integer
DATEIND       99- 99   Integer
EVENT        101-119   Character
ALTIND       121-122   Character
BEFINFO      124-163   Character
BEFFLAG      164-164   Character
LINK         166-167   Character
AFTINFO      169-208   Character
AFTFLAG      209-209   Character
REFERENCE    211-235   Character
COMMENT      236-315   Character
UPDCOM       316-346   Character
UPDDATE      348-354   Character
------------------------------

These variables have the following definitions:

IGRAID     is the 11-character IGRA station identifier [e.g., CAM00071600 
           for Sable Island]. Within this file, the IGRA 2 station 
           identifier is Of the form ??M000#####, where

           ?? is the Federal Information Processing Standard (FIPS) country 
             code.  For a complete list of possible values, see 
             "igra2-countries.txt" in the pub/data/igra/v2 FTP directory.
           M is the network code for a WMO station ID (the only type of 
             stations for which station history information is currently
             available).
           ##### is the most recent WMO station ID for the site.


WMOID      is the original WMO station identification number (e.g., 
           72600 for Sable Island before 1977, 71600 from 1977 on).

NAME       is the station name (often a city name; includes the state 
           abbreviation for U.S. stations).

NAMEFLAG   is the quality flag for the station name.  There are three
           possible values:

           Blank = no indication of questionable quality
           ?     = questionable
           c     = corrected

LATITUDE   is the latitude of the station (in decimal degrees,
           missing = 9999.0000).

LATFLAG    is the quality flag for the latitude. There are three
           possible values:

           Blank = no indication of questionable quality
           ?     = questionable
           c     = corrected

LONGITUDE  is the longitude of the station (in decimal degrees,
           missing = 9999.0000).

LONFLAG    is the quality flag for the longitude. There are three
           possible values:

           Blank = no indication of questionable quality
           ?     = questionable
           c     = corrected

ELEVATION  is the elevation of the station (in meters to tenths above 
           sea level, missing = 9999.0).

ELVFLAG    is the quality flag for the elevation. There are three
           possible values:

           Blank = no indication of questionable quality
           ?     = questionable
           c     = corrected

YEAR       is the year of the event.

MONTH      is the month of the event (99 = missing/unknown).

DAY        is the day of the event (99 = missing/unknown).

HOUR       is the hour of the event [in Universal Coordinated Time 
           (UTC), 99 = missing/unknown].

DATEIND    is the uncertain date indicator.  There are two possible 
           values:

           0 = reasonably certain.
           1 = original metadata source uncertain or unclear about the 
               date or the date was judged to be dubious.

EVENT      is the event type.  Event types are either dynamic (i.e.,
           reporting change) or static (i.e., reporting a practice or 
           equipment in use at the time of the event date).  The
           following 43 event types are currently used in the file:

           CHANGE BALLOON TYPE = change in balloon material, size, or 
                                 weight.
           CHANGE COMPUTER     = change in computing system.
           CHANGE CORD LENGTH  = change in length of suspension court 
                                 between balloon and instrument.
           CHANGE CORRECTION   = change in data correction.
           CHANGE DATA CUTOFF  = change in data cutoff (i.e., temperature 
                                 or humidity threshold below or above 
                                 which measurements are not reported.
           CHANGE FREQUENCY    = change in radio frequency of operations.
           CHANGE GRAVITY VAL. = change in gravitational constant.
           CHANGE GROUND EQUIP = change in ground equipment.
           CHANGE ID NUMBER    = change in station identification number.
           CHANGE OBS. TIME    = change in observation time.
           CHANGE OPERATOR     = change in entity responsible for station.
           CHANGE P SENSOR     = change in pressure sensor.
           CHANGE RADIAT. CORR = change in radiation correction.
           CHANGE REPOR. PRAC. = change in reporting practice.
           CHANGE RH ALGORITHM = change in relative humidity algorithm.
           CHANGE RH DUCT      = change in type of duct for relative 
                                 humidity sensor.
           CHANGE RH SENSOR    = change in relative humidity sensor.
           CHANGE SONDE MODEL  = change in radiosonde model.
           CHANGE T DUCT       = change in type of duct for the 
                                 temperature sensor.
           CHANGE WIND EQUIP.  = change in equipment used for
                                 determining winds.
           END OF PROBLEM      = end of a problem.
           MISCELLANEOUS       = miscellaneous metadata, including 
                                 national independence dates.
           OBS. PROG. REDUCED  = observation program reduced.
           OBS. RESUMED        = observations resumed after suspension.
           OBS. SUSPENDED      = observations suspended.
           OPERATED BY         = entity responsible for station on event 
                                 date.
           START OF PROBLEM    = start of a problem.
           STATION CLOSED      = observations discontinued at station.
           STATION MOVED       = change in station location.
           STATION OPENED      = observations initiated at station.
           USING BALLOON TYPE  = balloon material, size, or weight in 
                                 use on the event date.
           USING COMPUTER      = computing system in use on the event 
                                 date.
           USING DATA CUTOFF   = data cutoff in use on the event date.
           USING GROUND EQUIP. = ground equipment in use on the event 
                                 date.
           USING OBS. TIME     = observation time(s) in use on the event 
                                 date.
           USING P SENSOR      = pressure sensor in use on the event date.
           USING RADIAT. CORR. = radiation correction in use on the event 
                                 date.
           USING REPOR. PRAC.  = reporting practice in use on the event 
                                 date.
           USING RH ALGORITHM  = relative humidity algorithm in use on 
                                 the event date.
           USING RH SENSOR     = relative humidity sensor in use on the 
                                 event date.
           USING SONDE MODEL   = radiosonde model in use on the event 
                                 date.
           USING T SENSOR      = temperature sensor in use on the event 
                                 date.
           USING WIND EQUIP.   = equipment used for determining winds 
                                 on the event date.

ALTIND     is the alternates indicator. This two-character indicator is 
           used in cases in which an event type appears more than once 
           for a particular station and date, and the information 
           provided in the before/after fields differs among instances. 
           The first character of the indicator represents the type of 
           event that is recurring. It has 11 possible values:

           Blank = not used.
           B = balloon Type.
           C = computing system.
           G = ground equipment.
           H = Relative humidity algorithm.
           I = instrument.
           P = reporting practice.
           R = radiation correction.
           S = sensor.
           W = wind equipment.
           X = other.

           The second character is a digit representing the index of 
           recurrence (e.g., 1 = first instance, 2 = second instance, 
           etc.).  When an event type only appears once for a specific
           station and date, the indicator may be set to the 
           appropriate characters for the first instance, or both 
           characters are set to blank.

BEFINFO    is the before information.  For events indicating a change, 
           this is the practice/equipment in use prior to the event date.
           For "static" events, it reflects the practice/equipment in use
           around the time of the event date.  Note that for the STATION 
           MOVED event type, this field has historically been left blank 
           since the coordinates for the period prior to the event date 
           are contained in the previous record for the station.  See 
           Tables 4-16 in Gaffen (1996) for many examples of the entries 
           in this field.

BEFFLAG    is the quality flag for the before information.  There are
           three possible values:

           Blank = no indication of questionable quality
           ?     = questionable
           C     = corrected

LINK       is the link between the before and after information fields. 
           It has the following two possible values:

           Blank = no after information follows.
           TO = after information follows.

AFTINFO    is the after information.  For events indicating a change, 
           this is the information for the period beginning on the event 
           date.  For "static" events, this field is blank.  Note that 
           for the STATION MOVED event type, this field has historically 
           been left blank since the coordinates for the period beginning 
           on the event date are contained in the same record for the 
           station.  See Tables 4-16 in Gaffen (1996) for many examples 
           of the entries in this field.

AFTFLAG    is the quality flag for the after information.  There are
           three possible values:

           Blank = no indication of questionable quality
           ?     = questionable
           C     = corrected

REFERENCE  is the citation of a document, website, organization, or 
           individual from which the information was obtained.

COMMENT    is a text field for additional notes.

UPDCOM     is a text field for notes referring to changes made to a 
           previously existing record.

UPDDATE    is a field containing the month and year (MM/YYYY) during 
           which the record was last updated.

------------------------------------------------------------------------
III. Version History
------------------------------------------------------------------------

Version 3.0 (August 2014)

- Station history information from Gaffen (1996) was added for stations 
  represented in IGRA 2 that were not represented in IGRA 1. These records 
  have an update date of 99/1996 and an update comment "from Gaffen 
  (1996) for IGRA 2". While the spelling of event types in these records 
  was adjusted to comply with the event types listed in the documentation,
  no effort was made to standardize the before and after information in
  these records.

- The format of existing and new records was adjusted to allow for the 
  11-character IGRA 2 station identifiers, eliminate the country code 
  and country code flag fields (since the country code is now contained in 
  the station ID), and change the elevation from an integer in whole meters 
  to a real number in meters to tenths. 


Version 2.1 (October 5, 2010)

- Thanks to Liangying Zhang of NCAR, the metadata for U.S. and Australian 
  stations were updated during the summer of 2010. The 475 added or edited 
  records are identified with an update date of 06/2010 and a reference of 
  "Updated by NCAR/EOL". Updates are based on information received by NCAR 
  from the U.S. National Weather Service and the Australian Bureau of 
  Meteorology.


Version 2.0 (November 2009):

- A total of 2763 events supplied by Steve Schroeder in February 2007 and 
  some additional events received from WMO member countries during 2006 
  and 2007 were added.

- The lengths of the "before information" and "after information" fields 
  were increased to 40 characters each, and the formatting and spelling of 
  entries in those fields (e.g., instrument names) were standardized.

- Two sets of records that appear to have been inserted automatically but 
  do not add to the value of the station history information were removed.
  The first set includes records identifying a change in a station's 
  geopolitical affiliation that carried a year prior to 1900 or whose year 
  was equal to 9999.  The second set consists of all "Station opened" and 
  "Station closed" events attribute it to "NOAA NCDC" since they appear to 
  be based on often spurious changes in coordinates.

- Event types whose spelling did not correspond with Table 1 of Gaffen 
  (1996) were corrected.

- A variety of additional minor format inconsistencies were corrected.

- The documentation was expanded considerably to include a more detailed
  description of the fields, additional background information, a version
  history, and a list of all references corresponding to citations of
  publications that appear in the metadata file.


Version 1.0 (released February 2006):

- The original Gaffen (1996) digital file of station history information 
  was reformatted to include "day," "hour," "update date," and "update 
  comment" field and to convert longitude to decimal degrees ranging from 
  -180 to 180.

- Updates to records for GUAN and RATPAC stations were added wherever 
  possible.

- Some of the original Gaffen (1996) records were removed if they were
  unnecessary given previous records or given the newly received 
  information.

------------------------------------------------------------------------
IV. Background
------------------------------------------------------------------------

The IGRA metadata consist of three principal types of radiosonde station
history information.

1. The primary source is Gaffen (1996):  Records from this source are 
   identified by an update date of 99/1996.

2. Updates to records for GUAN and RATPAC stations (Free et al. 2005) for 
   the period since Gaffen (1996):  Most of these records are identified 
   by a source attribution of Hammer (personal communication) and are 
   based on information received since 2004 through communication between 
   the NCDC GCOS Lead Center and GCOS focal points at Hydrological and 
   Meteorological Service Centers (HMSCs) in WMO member countries. 
   Additional sources of updated information include Joyce (personal 
   communication) and NOAA/NWS.

3. Events supplied by Steve Schroeder of Texas A&M University: 
   Identified by a source attribution of Schroeder (2007), these events 
   cover stations in the Russian Federation, India, Japan, China 
   (including Hong Kong and Taiwan), and Antarctic stations operated by 
   those countries.

Cautionary notes:

1. Radiosonde station history information is generally received in a
   variety of formats and to varying degrees of specificity.  
   Consequently, the completeness, precision, and accuracy of IGRA 
   metadata records also vary among stations and over time.

2. Although station history information is listed by IGRA station identifier,
   no attempt has been made to reconcile locations and dates in station 
   history information records with station locations and data availability 
   in IGRA 2. The presence of the station history event in 
   the station history file does not necessarily imply that data are
   available in IGRA at the time of the event.

3. Gaffen (1996) aimed to reveal inconsistencies and errors in sources 
   of metadata but not to correct them, and the IGRA metadata are a 
   reflection of this approach.

4. Different station catalogs often disagree about the exact locations of
   stations, and the number of small location or elevation discrepancies 
   is too large to hope to resolve.  While a large number of discrepancies 
   can be traced to differences in rounding methods, it is probable that 
   many small location errors arise from interpreting a surface observing 
   location as an upper air location or vice versa.

5. The Definition of ground equipment is often ambiguous.  The ground 
   system and radar may carry separate names, or the entire ground system 
   may be referred to by the name of the radar, or the radar may be 
   referred to by the name of the ground system.  In addition, a 
   radiosonde is sometimes referred to by the name of the ground system 
   it uses (such as an AN/GMD-1A radiosonde), implying that any radiosonde 
   compatible with that type of ground equipment may have been used.

6. The current country code is used in all of a station's metadata 
   records even if the station has been under the control of different 
   countries throughout its history.  Significant changes in control 
   are noted in station names or comments.


------------------------------------------------------------------------
V. References
------------------------------------------------------------------------

The following are full literature citations for the abbreviated 
references used in the IGRA metadata file as well as in this 
documentation:

CIA (Central Intelligence Agency), 1993: The World Factbook 1993. 489 
   pp. plus maps. [Available from National Technical Information Service, 
   5285 Port Royal Road, Springfield, VA 22161, Tel. (703) 487-4650.]

Dobesch, H., E. Rudel, and K. Zimmermann, 1992: Radiosounding in Austria: 
   A historical review of instruments and data. Papers presented at the 
   WMO Technical Conference on Instruments and Methods of Observation 
   (TECO-92), Vienna, Austria, 11-15 May 1992, WMO/TD - No. 462. 
   Instruments and Observing Methods Report No. 49, pp. 431-435. World 
   Meteorological Organization, Geneva, Switzerland.

Free, M., D.J. Seidel, J.K. Angell, J. Lanzante, I. Durre, and T.C. 
   Peterson, 2005: Radiosonde Atmospheric Temperature Products for 
   Assessing Climate (RATPAC): A new data set of large-area anomaly time 
   series. J. Geophys. Res., 110, D22101, doi:10.1029/2005JD006169.

Gaffen, D.J., 1993: Historical changes in radiosonde instruments and
   practices.  WMO/TD-No. 541. Instruments and Observing Methods Report 
   No. 50. World Meteorological Organization, Geneva, Switzerland, 123 pp.

Gaffen, D.J., 1996: A digitized metadata set of global upper-air station
   histories. NOAA Technical Memorandum ERL ARL-211. [Available online 
   from http://www.ncdc.noaa.gov/oa/climate/igra/index.php?name=metadata.]

Miyagawa,K, 1990: A quantitative analysis of day-night temperature 
   differences observed by Japanese rawinsondes. Tenki, 2, 38-48. [NASA 
   Tech. Translation NASA-TT-21268, available from SCITRAN, P.O. Box 5456, 
   Santa Barbara, CA 93150, tel. (805) 969-2413.]

Oakley, T., 1993: Report by the rapporteur on radiosonde compatibility: 
   Part A, WMO catalogue of radiosondes and upper-air wind systems in use 
   by members (1993).  WMO/TD-No. 587, Instruments and Observing Methods 
   Report No. 56. World Meteorological Organization, Geneva, Switzerland, 
   89 pp.

Raj, Y.E.A., V. Mathew, and J.C. Natu, 1987: Discontinuities in 
   temperature and contour heights resulting from change of instruments 
   at Indian radiosonde stations. Mausam, 38, 407-410.

Schwartz, B.E., and M. Govett, 1992: A hydrostatically consistent North
   American radiosonde data base at the Forecast Systems Laboratory, 
   1946-present. NOAA Technical Memorandum ERL FSL-4, NOAA/ERL/FSL, 325 
   Broadway, Boulder, CO 80303, 81 pp.

Weather Bureau, 1979: Climate of South Africa: Part 13, Upper-air 
   statistics.  WB 39, U.D.C/U.D.K. 551-587(68), Research Division, 
   Weather Bureau, Department of Transport, Pretoria, South Africa, 99 pp.

Weather Bureau, 1990: Climate of South Africa: Part 14, Upper-air 
   statistics 1968-1987.
-------------------------------------------------------------------------
-------------------------------------------------------------------------
