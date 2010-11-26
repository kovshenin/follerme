import urllib, urllib2

from google.appengine.ext import db
from google.appengine.api import urlfetch

from models import Geo, Recent
import logging

def geocode():
	query = Geo.all()
	query.filter('geo =', 'None')
	results = query.fetch(1)
	for result in results:
		try:
			# If the location format is already a Geo string
			lat, lon = result.location.split(",")
			lat = float(lat)
			lon = float(lon)
			result.geo = "%s,%s" % (lat, lon)
			result.put()
			break
		except:
			pass
		
		# Prepare and fire a request to the Google Maps API
		form_fields = {'q': result.location.encode('utf-8'), 'output': 'csv', 'key': 'ABQIAAAAXG5dungCtctVf8ll0MRanhR9iirwL7nBc9d2R7_tFiOfa5aC4RSTKOF-7Bi7s8MaO5KAlewwElCpIA'}
		form_data = urllib.urlencode(form_fields)
		
		google_maps = urlfetch.fetch(url='http://maps.google.com/maps/geo?' + form_data)
		if google_maps.status_code == 200 and len(google_maps.content):
			try:
				# Parse and record the result if it's valid
				status, n, lat, lon = google_maps.content.split(',')
				result.geo = "%s,%s" % (lat, lon)
				result.put()
			except:
				pass

def create_geo(locations):
	# Create new entries into the Geo entity in the datastore.
	for location in locations:
		geo = Geo(location=location, geo='None')
		geo.put()
	
	logging.info('New locations have been added to the datastore: %s' % locations)

def create_recent(recent):
	
	if recent:
		r = Recent(screen_name=recent['screen_name'], profile_image_url=recent['profile_image_url'])
		r.put()
		
		logging.info('Recent entry has been added to the datastore: %s' % recent['screen_name'])
	
	# Let's do this in batch since we don't want too much datastore API on every request.
	recents = Recent.all()
	count = recents.count()
	if count > 80:
		recents.order('published')
		recents = recents.fetch(count - 40)
		db.delete(recents)
			
		logging.info('Removing some recent entries, was > 80, now < 40')
