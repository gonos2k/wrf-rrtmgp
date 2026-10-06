DESCRIPTION OF SOLRAD DAILY DATA FILES 

Contact:

John Augustine
NOAA GML 
325 Broadway Street
Boulder, CO 80305
email: john.a.augustine@noaa.gov
Phone: 720-238-6480

Use the following reference in any publications that use SOLRAD 
data (Note that SOLRAD was formerly called ISIS):

Hicks, B. B., J. J. DeLuisi, D. R. Matt, 1996: The NOAA Integrated 
Surface Irradiance Study (ISIS)--a new surface radiation monitoring 
program.  Bull. Amer. Meteor. Soc., 77, 2857-2864


DATA DISTRIBUTION:

Daily SOLRAD text data files for each station may be downloaded from GML 
at the following location:

https://gml.noaa.gov/aftp/data/radiation/solrad/

To get to a specific file, advance to the appropriate station directory, 
and then to the specific year directory, e.g., for Albuquerque 2003 data:
 https://gml.noaa.gov/aftp/data/radiation/solrad/abq/2003/

SOLRAD data are actually processed in near-real-time every 15 minutes. 
These real-time data files build during the day and have the same names 
and structure as the daily quality-controlled files on the GML FTP site, 
but they are not checked for quality, so use at your own risk. The real-
time data files are available at:

https://gml.noaa.gov/aftp/data/radiation/solrad/realtime/


FILENAME INFORMATION:

SOLRAD data files distributed by GML contain one day of data for one 
station.  The FTP directories from which SOLRAD data are distributed are 
organized by station and year. The naming convention for SOLRAD data 
filenames is "stayyjjj.dat", where sta is a three-letter station 
identifier, yy represents the last two digits of the year (i.e., 95 for 
1995, 00 for 2000), and jjj is the day of year. A "day of year" in a 
filename that is less than 100 would be preceded by one or two zeros, 
e.g., day 75 would appear as 075, day 2 would appear as 002 in the 
filename.  

"abq" is the station identifier for Albuquerque, New Mexico
"bis" is the station identifier for Bismarck, North Dakota
"hnx" is the station identifier for Hanford, California
"sea" is the station identifier for Seattle, Washington
"tlh" is the station identifier for Tallahassee, Florida
"slc" is the station identifier for Salt Lake City, Utah
"ste" is the station identifier for Sterling, Virginia
"msn" is the station identifier for Madison, Wisconsin
"ort" is the station identifier for Oak Ridge, Tennessee

For example, the file " abq95099.dat " contains data for Albuquerque
for day 99 of 1995 (9-Apr-1995).

SOLRAD data processing software is year 2000 compliant.  The year within 
the data files is written unambiguously with 4 digits on each line. 

The extension ".dat" is used because both radiation and meteorological 
data are included. The file " abq02099.dat " contains all of the 
radiation data for Albuquerque on day 99 of 2002 (9-apr-2002).  
  

DATA STRUCTURE:

SOLRAD data are organized into daily files of one- or three-minute data, 
and are written in ASCII text. Before 1-jan. 2015 the data were reported 
as 3-min averages; on and after 1-Jan. 2015, SOLRAD data are reported as 
1-min. averages of 1-sec. samples. 

The format was specified in such a way to ensure that all entries are  
separated by at least one space so that the files may be read with free 
format.   

SOLRAD follows the quality control (QC) philosophy of the BSRN. Bad data 
are deleted, but questionable data are only flagged. Integer QC flags 
follow each data point. The data files are written in ASCII. They may be 
read with the FORTRAN code shown below. The format was specified in such 
a way to ensure that all entries are separated by at least one space so 
that the files may be read with free format. Quality control parameters 
follow each measurement or calculated value. SOLRAD follows the quality 
control (QC) philosophy of the BSRN.  Instead of deleting questionable 
data, they are flagged.  A QC flag of zero indicates that the 
corresponding data point is good, having passed all QC checks. A value 
greater than 0 indicates that the data failed one level of QC. For 
example, a QC value of 1 could mean that the recorded value is beyond 
the physically possible range for that measurement. A value of 2 usually 
means that the data value failed the second level QC check, indicating 
that the data value may be physically possible but should be used with 
scrutiny, and so on. Missing values are indicated by -9999.9 and should 
always have a QC flag of 1. 

It is not unusual that thermopile-based solar pyranometers register a 
small negative signal at night. Most of this error is attributed to the 
thermopile cooling to space.  

This generally affects the global and diffuse solar measurements, if 
thermopile-based instruments are used for those measurements. This error 
is also present in daytime data, but its magnitude is difficult to 
determine.  Nighttime errors between 0 and -10 Wm^-2 are typical.  
Because this behavior is common, only nighttime signals that drop below 
the common range are flagged.

Daytime diffuse measurements made by thermopile-based pyranometers are 
also adversely affected as much as the global measurements. Because they 
are shaded, the cosine error caused by the solar beam is precluded, and 
thus Eppley model 8-48 pyranometer (notorious for its cosine error) can 
be used for the diffuse measurement. The Eppley model 8-48 pyranometer, 
which has been used for the diffuse measurement since the 2001 instrument 
exchanges, does not have this problem. The model 8-48 pyranometer relies 
on a differential signal between a black and a white surface on the 
detector. Since these two surfaces emit the same in the infrared, the 
differential signal owing to infrared cooling of the sensor's surface is 
zero. Thus, there is little or no offset owing to radiative cooling of 
the 8-48. 

The global solar sensor has the same infrared cooling problem, but solar 
heating inside of the dome during the day prevents development of a 
simple relationship using nighttime data that is applicable during the 
day. Direct solar heating is not a problem with the diffuse pyranometer 
because it is, by practice, shaded.  Therefore, the global solar 
measurement is not yet correctable, and should only be used in cases when 
the direct-normal and diffuse solar measurements are not available

On June 18, 2009, a pyrgeometer was added to the Madison complement of 
instruments and the UVB instrument was removed.  After that date, 
Madison's file format changed.

The following FORTRAN code may be used to read daily SOLRAD files EXCEPT
for Madison after 18 June 2009:

	parameter (nlines=1440)
	character*80 station_name
c
	integer year,month,day,jday,elevation,hr_to_LST,version
	integer min(nlines),hour(nlines)
c
	real	latitude,longitude,dt(nlines),zen(nlines)
      real direct(nlines)
	real	dw_psp(nlines)
	real	diffuse(nlines)
	real	uvb(nlines),uvb_temp_v(nlines)
c
	integer qc_direct(nlines)
	integer qc_dwpsp(nlines)
      integer qc_diffuse(nlines)
	integer qc_uvb(nlines)
	integer qc_uvb_temp(nlines)
c
c
      lun_in = 20
      open(unit=lun_in,file=[filename.dat],status='old',readonly)
c.
c.
c.
	read (lun_in,10) station_name
  10	format(1x,a)
	read(lun_in,*) latitude, longitude, elevation, hr_to_LST 
c
	icount = 0
	do i = 1,nlines
c	
	read(lun_in,30,end=40) year,jday,month,day,hour(i),min(i),dt(i),
     1 zen(i),dw_psp(i),qc_dwpsp(i),direct(i),qc_direct(i),
     2 diffuse(i),qc_diffuse(i),uvb(i),qc_uvb(i),uvb_temp(i),
     3 qc_uvb_temp(i),std_dw_psp(j),std_direct(j),std_diffuse(j),
     4 std_uvb(j)
c
	icount = icount + 1
c
  30  format(1x,i4,1x,i3,4(1x,i2),1x,f6.3,1x,f6.2,5(1x,f7.1,1x,i1),
     1 4(1x,f9.3))
c
	enddo
  40	type *,'end of file reached, ',icount,' records read'
.
.
.
c
c
c
c
c The following code can be used to read MADISON files AFTER 18 June 2009
c

	parameter (nlines=1440)
	character*80 station_name
c
	integer year,month,day,jday,elevation,hr_to_LST,version
	integer min(nlines),hour(nlines)
c
	real latitude,longitude,dt(nlines),zen(nlines)
      real direct(nlines)
	real	dw_psp(nlines)
	real	diffuse(nlines)
	real	uvb(nlines)
	real  uvb_temp_v(nlines)
	real	dpir(nlines) !Downwelling IR in Wm^-2
	real	dpirc(nlines)!PIR case temperature (K)
	real	dpird(nlines)!PIR dome temperature (K)
c
	integer qc_direct(nlines)
	integer qc_dwpsp(nlines)
      integer qc_diffuse(nlines)
	integer qc_uvb(nlines)
	integer qc_uvb_temp(nlines)
	integer qc_dpir(nlines)
	integer qc_dpirc(nlines)
	integer qc_dpird(nlines)
c
c
      lun_in = 20
      open(unit=lun_in,file=[filename.dat],status='old',readonly)
c.
c.
c.
	read (lun_in,10) station_name
  10	format(1x,a)
	read(lun_in,*) latitude, longitude, elevation, hr_to_LST 
c
	icount = 0
	do i = 1,nlines
c	
	read(lun_in,30,end=40) year,jday,month,day,hour(i),min(i),dt(i),
     1 zen(i),dw_psp(i),qc_dwpsp(i),direct(i),qc_direct(i),
     2 diffuse(i),qc_diffuse(i),uvb(i),qc_uvb(i),uvb_temp(i),
     3 qc_uvb_temp(i),dpir(i),qc_dpir(i),dpirc(i),qc_dpirc(i),dpird(i),
     4 qc_dpird(i),std_dw_psp(i),std_direct(i),std_diffuse(i),
     5 std_uvb(i),std_dpir(i),std_dpirc(i),std_dpird(i)
c
	icount = icount + 1
c
  30  format(1x,i4,1x,i3,4(1x,i2),1x,f6.3,1x,f6.2,8(1x,f7.1,1x,i1),
     1 7(1x,f9.3))
c
	enddo
  40	type *,'end of file reached, ',icount,' records read'
.
.
.

The SOLRRAD data file structure includes two header records; the first 
has the name of the station, and the second gives the station's latitude, 
longitude, elevation above mean sea level in meters, and the displacement 
in hours from local standard time. The files are organized in Universal 
Coordinated Time (UTC). These are followed by at most, 480 lines of data 
for 3-min. data and 1440 lines for 1-min. data (from 2015 on).

The date and time parameters and solar zenith angle are given on every 
line. Data are reported as 1-minute or 3-minute averages of one-second 
samples. Reported times are the end times of the 3-min. averaging 
periods, i.e., the data given for 0000 UTC are averaged over the period 
from 2357 or 2359 (of the previous UTC day) to 0000. The solar zenith 
angle is reported in degrees on each line of data. It is computed for the 
central time of the averaging period of the sampled data, i.e., 1.5 
minutes before the reported time on the line.  Missing-data periods 
within the files are not filled in with missing values, therefore, a file 
with missing periods will have fewer than 480 data records.  

Radiation values are reported to the tenths place.  Although this is 
beyond the accuracy of the instruments, data are reported in this manner 
in order to maintain the capability of backing out the raw voltages at 
the accuracy that they were originally reported.  Also, if the accuracies 
of the instruments improve to a fraction of a Wm^-2, the data format will 
not have to be changed.  

The variables, their data type, and description are given below:

station_name	character	station name, e. g., Goodwin Creek
latitude	real	latitude in decimal degrees (e. g., 40.80)
longitude	real	longitude in decimal degrees (e. g., 105.12)
elevation	integer	elevation above sea level in meters
h_to_lst	integer hours displaced from local standard time
year		integer	year, i.e., 2002
jday		integer	Julian day (1 through 365 [or 366])
month		integer	number of the month (1-12)
day		integer	day of the month(1-31)
hour		integer	hour of the day (0-23)
min		integer	minute of the hour (0-59)
dt		real	decimal time (hour.decimalminutes),e. g., 23.5 = 2330
zen		real	solar zenith angle (degrees)
dw_psp	real	downwelling global solar (Watts m^-2)
direct	real	direct solar (Watts m^-2)
diffuse	real	downwelling diffuse solar (Watts m^-2)
uvb		real	global UVB (milliWatts m^-2)
uvb_temp    real	UVB temperature (C) – 40-45 deg. C is normal
qc_dwpsp	integer quality control parameter for downwelling global 
solar (0=good)
qc_direct	integer quality control parameter for direct solar (0=good)
qc_diffuse	integer quality control parameter for diffuse solar (0=good)
qc_uvb	integer quality control parameter for UVB irradiance (0=good)
qc_uvb_temp	integer quality control parameter for the UVB instrument 
temperature (0=good)
std_dw_psp	real	standard deviation of the 1-sec. samples for global 
solar (dw_psp)
std_direct	real	standard deviation of the 1-sec. samples for direct 
solar
std_diffuse	real	standard deviation of the 1-sec. samples for diffuse 
solar
std_uvb real	standard deviation of the 1-sec. samples for uvb

for MADISON AFTER 18 June 2009:

dpir		real downwelling thermal IR (Watts m^-2)
dpirc		real downwelling PIR case temperature (K)
dpird		real downwelling PIR dome temperature (K)
std_dpir	real standard deviation of the 1-sec. samples for downwelling 
IR
std_dpirc	real standard deviation of the 1-sec. samples for PIR case 
temp
std_dpird	real standard deviation of the 1-sec. samples for PIR dome 
temp



All radiation parameters, except UVB, are reported in units of Watts m^-
2; UVB is reported in milliWatts m^-2.

The UVB flux is given as the total measured surface UVB flux convoluted 
with the erythemal action spectrum, i.e., that part of the UVB spectrum 
responsible for sunburns on human skin (erythema) and DNA damage. It is 
reported in this way because the response function of the UVB instrument 
approximates the erythemal action spectrum; thus the reported value is 
most representative of what the instrument is actually measuring.  

Erythemal UVB irradiance reported in SOLRAD data files is computed for 
300 Dobson units of ozone.  This is done because the ozone value over the 
stations is unknown during the near real-time processing.  If the ozone 
for a particular day is less than 300 Dobson units, then the reported UVB 
irradiance would be less than it should be. If the user would like to 
correct reported SOLRAD UVB measurements for the actual ozone, correction 
tables are available. Contact the webmaster for these tables.  

The field UVB instruments are calibrated against a triad of "standard" 
UVB instruments that are maintained by NOAA's Central UV Calibration 
Facility.  The standard instruments are periodically calibrated in the 
sun by comparing their broadband measurements to the integrated output of 
UV spectroradiometers.  These calibrations are transferred to the field 
instruments just before they are deployed in the network by operating 
them side-by-side for a few days.  To accomplish this transfer, a scale 
factor, which is simply a ratio of the test instrument's daily integral 
to that of the mean of the standards, is computed for each day that the 
test UVB instrument is run alongside the standards.  The mean of the 
daily scale factors is used to transfer the standards' well-maintained 
calibrations to the test instruments when they are deployed in the field.  

Mean calibration factors for the UVB standards are computed as a function 
of solar zenith angle, and are applied to the field instrument as such in 
the daily processing.  For example, to compute the UVB irradiance, the 
output voltage, is multiplied times the Standards' calibration factor for 
the solar zenith angle that the measurement was made, then that result is 
divided by the scale factor for that field instrument.  

The following table lists the UVB Standards' calibration information 
computed using the September 23, 1997 UV Spectroradiometer 
intercomparison data. 

erythemal    solar
conversion   zenith
factor       angle
(W m^-2 / V)

0.136        0.0 extrapolated
0.136        5.0
0.136        10.0 
0.135        15.0
0.134        20.0
0.133        25.0
0.132        30.0
0.131        35.0
0.130        40.0
0.129        45.0
0.128        50.0
0.128        55.0
0.129        60.0
0.132        65.0
0.138        70.0
0.147        75.0
0.164        80.0
0.191        85.0
0.220        90.0 extrapolated



QUALITY CONTROL AND QUALITY ASSURANCE

These data are provisional. NOAA has attempted to produce the best data 
set possible, however the data quality is constrained by measurement 
accuracies of the instruments and the quality of the calibrations.  
Regardless, NOAA attempts to ensure the best quality possible through 
quality assurance and data quality control.  The data are subjected to 
automatic procedures as the daily files are processed. At present, they 
are subjected only to a first-level check, and a daily "eye" check before 
being released, however, as quality control procedures become more 
refined, they will be applied, and new versions of the data files will be 
generated.  

Quality assurance methods are in place to ensure against premature 
equipment failure in the field and post deployment data problems. For 
example, all instruments at each station are exchanged for newly 
calibrated instruments on an annual or biannual basis. Calibrations are 
performed by world-recognized organizations. Pyranometers and 
pyrheliometers have been calibrated at the National Renewable Energy 
Laboratory (NREL) in Golden, Colorado, or the World Meteorological 
Organization's (WMO) Region 4 Regional Solar Calibration Center at NOAA 
in Boulder, Colo., which is maintained by GML. Calibration factors for 
the UVB instrument are transferred from three standards maintained by 
GML’s National UV Calibration Facility in Boulder. In general, all of the 
standards the GML and NREL are traceable to NIST, WMO, or their 
equivalent. 


INSTRUMENTS:

1.	The Yankee UVB Broadband Radiometer

The UVB radiometer measures erythemally weighted UVB irradiance in the 
range from 280 to 320 nm.  Field UVB instruments are calibrated by 
referencing them to three standard instruments that are rigorously 
maintained by NOAA's Central UV Calibration Facility. Calibrations for 
these instruments are applied as a function of solar zenith angle.  

2.	The Normal Incidence Pryheliometer (NIP)

The NIP measures direct solar radiation in the broadband spectral range 
from 280 to 3000 nm. Those used at SOLRAD stations are calibrated 
nominally on a biennial basis at the NOAA calibration facility in 
Boulder, CO

3.	Precision Spectral Pyranometer (PSP)

A PSP measures downwelling global irradiance at SOLRAD stations. 
These instruments are sensitive to the same broadband 
spectral range as the NIP, 280 to 3000 nm.  They are calibrated 
on a biennial basis at the NOAA calibration facility in Boulder, CO

An inherent problem with the PSP, or any radiometer with a single-black 
thermopile detector, is that its sensor cools to space (if itis directed 
upward) and this causes a negative signal.  This is apparent at night 
where it shows up as an erroneous negative irradiance that can be as high 
as -30 Wm^-2.  Daytime data also contain this error but it is overwhelmed 
by the large solar signal. This error especially affects the diffuse 
measurement made by a PSP because the sensor is shaded.  Therefore, the 
PSP is not used for the diffuse measurement.  

4.	Eppley 8-48 "black and white" pyranometer 

This pyranometer has been used for the diffuse solar measurement since 
2001. The 8-48 has been found to have desirable properties for this 
measurement because it does not use a solid black surface for the 
detector and thus does not have the "nighttime" offset problem. These 
instruments are sensitive to the same spectral range as the other 
broadband solar radiometers, 280 to 3000 nm. They are also calibrated on 
a yearly basis.  

5.      Precision Infrared Radiometer (PIR) 

The PIR measures and downwelling thermal infrared irradiance at Madison 
only. It is sensitive to the spectral range from 3000 to 50,000 nm. NOAA 
maintains three standard PIRs that are calibrated biennially by PMOD in 
Davos, Switzerland, and are used to calibrate field PIRs. 

Fair use policy, license, etc.:

Findable and Accessible:
SOLRAD data are freely available to users from the GML web-site 
(e.g. GML web-site, GRAD ftp data access). 

Fair Use:
These data are made freely available to the public and the 
scientific community in the belief that their wide dissemination 
will lead to greater understanding and new scientific insights. 
To ensure that GML receives fair credit for their work please 
include relevant citation text in publications (see below). We 
encourage users to contact the data providers, who can provide 
detailed information about the measurements and scientific 
insight. In cases where the data are central to a publication, 
co-authorship for data providers may be appropriate.

License: 
CC0 1.0 Universal - NOAA has recently adopted Creative Commons 
Zero 1.0 Universal Public Domain Dedication (CC0-1.0) licensing 
for all internally published datasets. These data were produced 
by NOAA and are not subject to copyright protection in the 
United States. NOAA waives any potential copyright and related 
rights in this data worldwide through the Creative Commons Zero 
1.0 Universal Public Domain Dedication (CC0 1.0).  

These data were produced by NOAA and are not subject to 
copyright protection in the United States. NOAA waives any 
potential copyright and related rights in this data worldwide 
through the Creative Commons Zero 1.0 Universal Public Domain 
Dedication (CC0-1.0).





