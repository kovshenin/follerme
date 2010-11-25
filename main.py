import re
import urllib, urllib2
import logging
import time
import os
import sys
from datetime import datetime
import itertools

# Google's API
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext.webapp import template

from google.appengine.api import urlfetch
from google.appengine.api.labs import taskqueue
from google.appengine.ext import deferred

# Twitter & OAuth
from oauth import oauth
from oauthtwitter import OAuthApi

# JSON is used to encode API responses and decode task requests
import simplejson.encoder
import simplejson.decoder

from models import Geo, Recent, Option
import tasks

# These two objects can be used globally
encoder = simplejson.encoder.JSONEncoder()
decoder = simplejson.decoder.JSONDecoder()

# API tokens and keys.
consumer_key = 'cKlpH5jndEfrnhBQrrp8w'
consumer_secret = 'reeYtKhTY7LRTwzXE5tmFrxwkD4lLVY9FgxrY5KFsE'
api_key = 'cKlpH5jndEfrnhBQrrp8w'
google_maps_key = 'ABQIAAAAXG5dungCtctVf8ll0MRanhS8x33voUDc7NMITWhA0MX8qZ_M_hTQt9MRazZ_htm3kW2tYUg8dmaDgA'

# The home screen, nothing extra-ordinary, we just render
# the template with an empty context.
class Home(webapp.RequestHandler):
	def get(self):
		context = {}
		render(self, 'home.html', context)
	
	# This is not magic. The request form's action on the home page
	# is set to the homepage itself via the POST method, this is the
	# place where we handle that request and redirect accordingly
	# to foller.me/username stripping extra characters. We get rid of
	# the "send post data" message by browsers when we refresh the profile.
	def post(self):
		profile_name = self.request.get('profile', None)
		if profile_name:
			if '@' in profile_name:
				profile_name = profile_name.replace('@', '')
			self.redirect(profile_name)
		else:
			self.redirect('/')

# The AJAX data handler, used to handle asynchronous requests such as
# the Google Maps (followers geography) part in the profile page. This
# can be extended in the future.
class Ajax(webapp.RequestHandler):
	def post(self, action):
		
		# If the request action is called gmap, calculate the followers' locations
		# and return them pointed out on a Google Map (via a template and javascript)
		if action == 'gmap':
			profile_name = self.request.get('profile', None)
			if profile_name:
				locations = {}
				twitter = getTwitterObject()
				followers = twitter.GetFollowers({'screen_name': profile_name})
				
				# Loop through each follower and add a location if it does not exist.
				# Otherwise add the user to the list on an existing location. This way
				# we're grouping followers from the same locations.
				for follower in followers:
					user = follower
					if follower['location'] in locations:
						locations[follower['location']]['users'].append(user)
					else:
						locations[follower['location']] = {'name': follower['location'], 'lat': 0, 'lon': 0, 'users': [user]}
				
				# Loop through all the locations and query the Datastore for their
				# Geo points (latitude and longitude) which could be pointed out
				# on the map.
				new_locations = []
				for location in locations.keys():
					query = Geo.all()
					query.filter('location =', location)
					g = query.get()
					
					# We don't want empty locations, neither do we want locations
					# recorded as None, which are temporary stored until the cron
					# jobs resolves them into valid geo points.
					if g:
						if g.geo != 'None':
							if g.geo != '0,0':
								# If a location exists, we set its lat and lon values that are then manipulated
								# via javascript and pointed out on the map.
								locations[location]['lat'], locations[location]['lon'] = g.geo.split(',')
							else:
								# If the location's geo address is 0,0 we remove it from the locations list
								# since we don't want to show irrelevant locations.
								del locations[location]
					
					# If the query returned no results, we verify if the location is valid
					# and add it to the Datastore with a value of None, for later processing
					# by the cron jobs. We delete the location from the locations dict anyways
					# since we don't have any lat,lon points to show off.
					else:
						if location:
							clean_location = location.replace('\n', ' ').strip()
							new_locations.append(clean_location)
						del locations[location]

				# Let's add tasks for new locations
				if new_locations:
					taskqueue.add(url='/admin/tasks/', params={'task': 'geo-create', 'locations': encoder.encode(new_locations)}, method='POST')
				
				render(self, 'map.html', {'locations': list(locations.values())})

# This simply redirects to our PB Wiki
class HomeAPI(webapp.RequestHandler):
	def get(self):
		self.redirect('http://follerme.pbworks.com/')
		
# Used to serve the API methods, mostly like the Profile class
# but less data is used.
class API(webapp.RequestHandler):
	def get(self, profile_name, request_object, response_format):
		context = {}
		
		# Create a Twitter OAuth object.
		try:
			twitter = getTwitterObject()
		except AttributeError, e:
			# Something went wrong, perhaps the OAuth tokens expired or have been removed
			# from the datastore.
			error = {'title': "Something's Broken", 'message': "We're so sorry, but it seems that Foller.me is down. We'll deal with this issue as soon as possible"}			
			logging.critical("API: Cannot create a Twitter OAuth object. Lacking tokens?")
			
			rendertext(self, encoder.encode({'error': error}))
			return

		# Fire a /statuses/user_timeline request, record parse the first entry for the user
		# details.
		try:
			timeline = twitter.GetUserTimeline({'screen_name': profile_name, 'count': 100})
		except urllib2.HTTPError, e:
			# An HTTP error can occur during requests to the Twitter API.
			# We handle such errors here and log them for later investigation.
			error = {'title': 'Unknown Error', 'message': "We're sorry, but an unknown error has occoured. We'll very be glad if you <a href='http://twitter.com/kovshenin'>report this</a>."}
			if e.code == 401:
				error['title'] = 'Profile Protected'
				error['message'] = "It seems that @%s's tweets are protected." % profile_name
			elif e.code == 404:
				error['title'] = 'Profile Not Found'
				error['message'] = 'It seems that @%s is not tweeting at all.' % profile_name
			
			# Log the error, render the template and return
			logging.warning("API: Code %s: %s - " % (e.code, e.msg) + "Request was: %s" % profile_name)
			rendertext(self, encoder.encode({'error': error}))
			return
		
		try:	
			profile = timeline[0]['user']
		except IndexError, e:
			# If timeline[0] is inaccessible then there were no tweets at all
			error = {'title': 'Profile Empty', 'message': "There were no tweets by @%s at all." % profile_name}
			logging.warning("API: Accessed an empty profile: %s" % profile_name)
			rendertext(self, encoder.encode({'error': error}))
			return
		
		# We make some manipulations for the profile, since we don't want to output some fields
		# (such as the created at field) the way Twitter passes them over to us. We convert that
		# into a valid datetime object.
		profile['created_at'] = datetime.strptime(profile['created_at'], "%a %b %d %H:%M:%S +0000 %Y")
		context['profile'] = profile
		
		# Let's submit this as a recent query into the datastore (via the task queue api)
		taskqueue.add(url='/admin/tasks/', params={'task': 'recent-create', 'recent': encoder.encode({'screen_name': profile['screen_name'], 'profile_image_url': profile['profile_image_url']})}, method='POST')
	
		# The data string will hold all our text concatenated. Perhaps this is not the fastest way
		# as strings are unchangable. Might convert this to a list in the future and then join if needed.
		data = ""
		for entry in timeline:
			data += " %s" % entry['text']
		
		# Remove all the URLs first
		p = re.compile(r'((https?|ftp|gopher|telnet|file|notes|ms-help):((//)|(\\\\))+[\w\d:#@%/;$()~_?\+-=\\\.&]*)')
		data = p.sub('', data)
		
		# Let's remove everything that doesn't match characters we allow.
		p = re.compile(r'[\-\.\,\!\?\+\=\[\]\/\'\"]') # Add foreign languages here
		data = p.sub(' ', data)
		
		# Remove all the stopwords and lowercase the data.
		data = remove_stopwords(data)
		data = data.lower()
		
		# The three dicts will hold our words and the number of times they've
		# been used for later tag cloud generation.
		topics = {}
		mentions = {}
		hashtags = {}
		
		# Loop through all the words, separate them into topics, hashtags and mentions.
		for word in data.split():
			if word.startswith('@'):
				d = mentions
			elif word.startswith('#'):
				d = hashtags
			else:
				d = topics
				
			if word in d:
				d[word] += 1
			else:
				d[word] = 1
		
		# What are we requesting?
		if request_object == 'topics':
			data = topics
		elif request_object == 'mentions':
			data = mentions
		elif request_object == 'hashtags':
			data = hashtags
		elif request_object == 'all':
			data = topics
			data.update(mentions)
			data.update(hashtags)
			
		# Let's see if we need to exclude anything
		exclude = self.request.get('exclude', '')
		for word in exclude.split(","):
			m_word = '@' + word
			h_word = '#' + word
			if word in data:
				del data[word]
			if m_word in data:
				del data[m_word]
			if h_word in data:
				del data[h_word]
		
		# Respond
		if response_format == 'json':
			rendertext(self, encoder.encode(data))
		elif response_format == 'xhtml':
			min_font_size = int(self.request.get('font_min', 12))
			max_font_size = int(self.request.get('font_max', 30))
			rendertext(self, get_cloud_html(data, min_font_size=min_font_size, max_font_size=max_font_size))

# Perhaps the most complex view. This is the profile view with the topics, hashtags
# and mentions clouds, user data and the followers geography.
class Profile(webapp.RequestHandler):
	def get(self, profile_name):
		
		# Prepare the context with our API keys used in the template.
		context = {'google_maps_key': google_maps_key, 'api_key': api_key}
		
		# Create a Twitter OAuth object.
		try:
			twitter = getTwitterObject()
		except AttributeError, e:
			# Something went wrong, perhaps the OAuth tokens expired or have been removed
			# from the datastore.
			error = {'title': "Something's Broken", 'message': "We're so sorry, but it seems that Foller.me is down.<br />We'll deal with this issue as soon as possible"}			
			logging.critical("Cannot create a Twitter OAuth object. Lacking tokens?")
			
			render(self, 'error.html', {'error': error})
			return

		# Fire a /statuses/user_timeline request, record parse the first entry for the user
		# details.
		try:
			timeline = twitter.GetUserTimeline({'screen_name': profile_name, 'count': 100})
		except urllib2.HTTPError, e:
			# An HTTP error can occur during requests to the Twitter API.
			# We handle such errors here and log them for later investigation.
			error = {'title': 'Unknown Error', 'message': "We're sorry, but an unknown error has occoured.<br />We'll very be glad if you <a href='http://twitter.com/kovshenin'>report this</a>."}
			if e.code == 401:
				error['title'] = 'Profile Protected'
				error['message'] = "It seems that @<strong>@%s</strong>'s tweets are protected.<br />Sorry, but there's nothing we can do at this point ;)" % profile_name
			elif e.code == 404:
				error['title'] = 'Profile Not Found'
				error['message'] = 'It seems that @<strong>%s</strong> is not tweeting at all.<br />Perhaps you should try somebody else:' % profile_name
			
			# Log the error, render the template and return
			logging.warning("Code %s: %s - " % (e.code, e.msg) + "Request was: %s" % profile_name)
			render(self, 'error.html', {'error': error})
			return
		except urlfetch.DownloadError, e:
			error = {'title': 'Overload Error', 'message': "We're sorry but it seems that we're overloaded.<br />Give us a few minutes and try again later."}
			logging.warning("Download Error: %s" % e)
			render(self, 'error.html', {'error': error})
			return
		
		try:	
			profile = timeline[0]['user']
		except IndexError, e:
			# If timeline[0] is inaccessible then there were no tweets at all
			error = {'title': 'Profile Empty', 'message': "There were no tweets by @<strong>%s</strong> at all.<br />Perhaps it's a newly created account, give them some time..." % profile_name}
			logging.warning("Accessed an empty profile: %s" % profile_name)
			render(self, 'error.html', {'error': error})
			return
		
		# We make some manipulations for the profile, since we don't want to output some fields
		# (such as the created at field) the way Twitter passes them over to us. We convert that
		# into a valid datetime object.
		profile['created_at'] = datetime.strptime(profile['created_at'], "%a %b %d %H:%M:%S +0000 %Y")
		context['profile'] = profile
		
		# Let's submit this as a recent query into the datastore (via a task)
		taskqueue.add(url='/admin/tasks/', params={'task': 'recent-create', 'recent': encoder.encode({'screen_name': profile['screen_name'], 'profile_image_url': profile['profile_image_url']})}, method='POST')
		
		# Let's get a list of 40 recent queries
		recents = []
		recent_screen_names = []
		query = Recent.all()
		query.order('-published')
		for recent in query:
			if recent.screen_name not in recent_screen_names:
				recents.append(recent)
				recent_screen_names.append(recent.screen_name)
				if len(recents) >= 40:
					break
		#recents = query.fetch(40)
		
		context['recents'] = recents
		
		# The data string will hold all our text concatenated. Perhaps this is not the fastest way
		# as strings are unchangable. Might convert this to a list in the future and then join if needed.
		data = ""
		for entry in timeline:
			data += " %s" % entry['text']
		
		# Remove all the URLs first
		p = re.compile(r'((https?|ftp|gopher|telnet|file|notes|ms-help):((//)|(\\\\))+[\w\d:#@%/;$()~_?\+-=\\\.&]*)')
		data = p.sub('', data)
		
		# Let's remove everything that doesn't match characters we allow.
		p = re.compile(r'[\-\.\,\!\?\+\=\[\]\/\'\"]') # Add foreign languages here
		data = p.sub(' ', data)
		
		# Remove all the stopwords and lowercase the data.
		data = remove_stopwords(data)
		data = data.lower()
		
		# The three dicts will hold our words and the number of times they've
		# been used for later tag cloud generation.
		topics = {}
		mentions = {}
		hashtags = {}
		
		# Loop through all the words, separate them into topics, hashtags and mentions.
		for word in data.split():
			if word.startswith('@'):
				d = mentions
			elif word.startswith('#'):
				d = hashtags
			else:
				d = topics
				
			if word in d:
				d[word] += 1
			else:
				d[word] = 1
		
		# Provide the context with th ready cloud HTMLs for topics, hashtags and mentions.
		# Then finally render the template.
		try:
			context['topics_cloud_html'] = get_cloud_html(topics)
		except:
			pass
		
		try:
			context['mentions_cloud_html'] = get_cloud_html(mentions, url="/%s")
		except:
			pass
		
		try:
			context['hashtags_cloud_html'] = get_cloud_html(hashtags)
		except:
			pass
				
		render(self, "profile.html", context)

# Used to render the about page
class About(webapp.RequestHandler):
	def get(self):
		render(self, 'about.html')

# This section (/admin/) is used for administration and moderation
# operations. Use with care, protect with password. OAuth registration
# and verification are handled here.
class Admin(webapp.RequestHandler):
	def post(self, action):
		
		# Tasks workers, stuff that is actually executed by the Task Queue API
		if action == 'tasks':
			
			# Create new entries into the Geo entity in the datastore. Moved here
			# to take load off the gmaps AJAX request.
			if self.request.get('task') == 'geo-create':
				locations = decoder.decode(self.request.get('locations', '[]'))
				
				for location in locations:
					geo = Geo(location=location, geo='None')
					geo.put()
				
				logging.info('New locations have been added to the datastore: %s' % locations)
				rendertext(self, 'New locations have been added to the datastore')
				
			# Create an entry to the Recents entity in the datastore, we moved this here
			# to take load off the profile request page.
			if self.request.get('task') == 'recent-create':
				recent = decoder.decode(self.request.get('recent'))
				if recent:
					r = Recent(screen_name=recent['screen_name'], profile_image_url=recent['profile_image_url'])
					r.put()
					
					logging.info('Recent entry has been added to the datastore: %s' % recent['screen_name'])
					
				rendertext(self, 'Recent entry have been processed')
				
			# Parse existing Geo entities with None as lat, lon, try to
			# geocode them from Google Maps API
			elif self.request.get('task') == 'geocode':
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
					
					# Google Maps doesn't like too many requests
					#time.sleep(1)

				rendertext(self, "Geo locations job complete")

	def get(self, action):
		# Depending on the action requested /admin/<action>/
		if action == 'register':
			
			# Register a Twitter user with the application using
			# OAuth. Works with the Option model to store the request and
			# access tokens.
			
			# Remove all the previous tokens matching oauth-* from the datastore.
			options = Option.all()
			options.filter('name >=', 'oauth-').filter('name <', 'oauth-' + u'\ufffd')
			options.fetch(1000)
			for option in options:
				option.delete()
			
			# Request an OAuth token and show the authorization URL on Twitter.
			twitter = OAuthApi(consumer_key, consumer_secret)
			credentials = twitter.getRequestToken()
			url = twitter.getAuthorizationURL(credentials)
			self.response.out.write('<a href="%s">%s</a>' % (url, url))
			
			# Save the tokens to the datastore for later authentication
			oauth_token = credentials['oauth_token']
			oauth_token_secret = credentials['oauth_token_secret']
			
			# Record the tokens
			opt = Option(name='oauth-request-token', value=oauth_token)
			opt.put()
			opt = Option(name='oauth-request-token-secret', value=oauth_token_secret)
			opt.put()
			
		elif action == 'verify':
			# Used to verify an initiated registration request. Request tokens should
			# by now be stored in the data store. Retrieve them and initiate a change.
			twitter = OAuthApi(consumer_key, consumer_secret)
			oauth_verifier = self.request.get('oauth_verifier')
			
			options = Option.all()
			options.filter('name =', 'oauth-request-token')
			oauth_token = options.get()
			
			options = Option.all()
			options.filter('name =', 'oauth-request-token-secret')
			oauth_token_secret = options.get()
			
			# Form a request and ask Twitter to exchange request tokens for access tokens using
			# an OAuth verifier (PIN code).
			credentials = {'oauth_token': oauth_token.value, 'oauth_token_secret': oauth_token_secret.value, 'oauth_callback_confirmed': 'true'}
			credentials = twitter.getAccessToken(credentials, oauth_verifier)
			
			# Record the access tokens and remove the previously stored request tokens.
			access_token = Option(name='oauth-access-token', value=credentials['oauth_token'])
			access_token_secret = Option(name='oauth-access-token-secret', value=credentials['oauth_token_secret'])
			
			oauth_token.delete()
			oauth_token_secret.delete()
			access_token.put()
			access_token_secret.put()
			
			# Tokens are now saved, getTwitterObject can be used.
			self.response.out.write("You are now registered as @%s!" % credentials['screen_name'])
		
		# Uses the Task Queues API
		elif action == 'cron':
			if self.request.get('task') == 'geocode':
				#def geocode_queue_add():
				#	taskqueue.add(queue_name='geocoding', url='/admin/tasks/', params={'task': 'geocode'}, method='POST')
					
				for i in range(2, 100, 2):
					deferred.defer(tasks.geocode, _countdown=i, _queue='geocoding')
				
				rendertext(self, "Geo task added to queue")

# Used to render templates with a global context
def render(obj, tpl='default.html', context={}):
	obj.response.out.write(template.render('templates/' + tpl, context))

# Used to render plain text (mostly for debugging purposes)
def rendertext(obj, text):
	obj.response.out.write(text)


# Returns a valid (authenticated) twitter object
def getTwitterObject():
	options = Option.all()
	options.filter('name =', 'oauth-access-token')
	access_token = options.get()

	options = Option.all()
	options.filter('name =', 'oauth-access-token-secret')
	access_token_secret = options.get()

	twitter = OAuthApi(consumer_key, consumer_secret, access_token.value, access_token_secret.value)
	return twitter
	
# Remove stopwords (list in stopwords.py)
def remove_stopwords(text):
	from stopwords import stopwords
	words = text.split()
	clean = []
	for word in words:
		if not word.isdigit() and not word.lower().encode("utf-8") in stopwords and not len(word) < 2:
			clean.append(word)
			
	return ' '.join(clean)

# Render a cloud based on a words dictionary. There seems to be some
# magic going on here, have to revise and probably rewrite for easier
# to understand and more elegant output.
def get_cloud_html(words, url="http://search.twitter.com/search?q=%s", min_font_size=12, max_font_size=30):
	maximum = max(words.values())
	minimum = min(words.values())
	
	count = len(words)
	
	if count > 100:
		min_output = 3
	elif count > 30:
		min_output = 2
	else:
		min_output = 1
		
	spread = maximum - minimum
	if spread == 0: 
		spread = 1
		
	step = (max_font_size - min_font_size) / float(spread)
	
	result = []
	
	for word, c in words.items():
		if c > (min_output - 2):
			size = min_font_size + ((c - minimum) * step)
			word_url = word.replace('@', '').replace('#', '')
			rel = "external nofollow" if url.startswith('http://') else ''
			result.append('<a rel="%(rel)s" style="font-size: %(size)spx" class="tag_cloud" href="%(url)s" title="\'%(word)s\' has been used %(count)s times">%(word)s</a>' % {'size': int(size), 'word': word, 'url': url % word_url, 'count': c, 'rel': rel})
			
	return ' '.join(result)

# Accessible URLs, others in app.yaml

urls = [
	(r'/', Home),
	(r'/admin/(\w+)/?', Admin),
	(r'/ajax/(\w+)/?', Ajax),
	(r'/about/?', About),
	(r'/(\w+)/?', Profile),
]

api_urls = [
	(r'/', HomeAPI),
	(r'/admin/(\w+)/?', Admin),
	(r'/(\w+)/(hashtags|mentions|topics|all)\.(json|xhtml)/?', API),
]

application = webapp.WSGIApplication(urls, debug=True)
application_api = webapp.WSGIApplication(api_urls, debug=True)

# Let's do some profiling
def profile_main():
    # This is the main function for profiling
    # We've renamed our original main() above to real_main()
    import cProfile, pstats, StringIO
    prof = cProfile.Profile()
    prof = prof.runctx("real_main()", globals(), locals())
    stream = StringIO.StringIO()
    stats = pstats.Stats(prof, stream=stream)
    stats.sort_stats("cumulative")  # Or cumulative
    stats.print_stats(80)  # 80 = how many to print
    # The rest is optional.
    # stats.print_callees()
    # stats.print_callers()
    #logging.info("Profile data:\n%s", stream.getvalue())
    print "<!--\nProfile data:\n%s\n-->" % stream.getvalue()

# Run the application
def real_main():
	# Use the following two lines for debugging the API locally
	#run_wsgi_app(application_api)
	#return
	try:
		if os.environ['HTTP_HOST'] == 'api.foller.me':
			run_wsgi_app(application_api)
		else:
			run_wsgi_app(application)
	except KeyError, e:
		run_wsgi_app(application)

main = profile_main

if __name__ == '__main__':
	main()
