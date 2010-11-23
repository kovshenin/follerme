import urllib, urllib2

from google.appengine.api import urlfetch

from models import Geo
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
