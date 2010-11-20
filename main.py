import re
import urllib
import logging
import time

from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext.webapp import template

from google.appengine.ext import db
from google.appengine.api import urlfetch
from google.appengine.api.labs import taskqueue

from oauth import oauth
from oauthtwitter import OAuthApi

consumer_key = 'cKlpH5jndEfrnhBQrrp8w'
consumer_secret = 'reeYtKhTY7LRTwzXE5tmFrxwkD4lLVY9FgxrY5KFsE'

class Home(webapp.RequestHandler):
	def get(self):
		context = {}
		render(self, 'home.html', context)
	
	def post(self):
		profile_name = self.request.get('profile', None)
		if profile_name:
			if '@' in profile_name:
				profile_name = profile_name.replace('@', '')
			self.redirect(profile_name + '/')
		else:
			self.redirect('/')
			
class Ajax(webapp.RequestHandler):
	def post(self, action):
		if action == 'gmap':
			profile_name = self.request.get('profile', None)
			if profile_name:
				locations = {}
				twitter = getTwitterObject()
				followers = twitter.GetFollowers()
				for follower in followers:
					if follower['location'] in locations:
						locations[follower['location']]['users'].append(follower['screen_name'])
					else:
						locations[follower['location']] = {'name': follower['location'], 'lat': 0, 'lon': 0, 'users': [follower['screen_name']]}
						
				for location in locations.keys():
					query = Geo.all()
					query.filter('location =', location)
					#query.filter('geo !=', 'None')
					g = query.get()
					if g:
						if g.geo != 'None':
							geo = g.geo
							locations[location]['lat'], locations[location]['lon'] = geo.split(',')
					else:
						if location:
							geo = Geo(location=location, geo="None")
							geo.put()
						del locations[location]
						
					#points.append({'screen_name': follower['screen_name'], 'location': follower['location']})
				logging.error(locations)
				render(self, 'map.html', {'locations': list(locations.values())})
			

class Profile(webapp.RequestHandler):
	def get(self, profile_name):
		context = {'profile_name': profile_name}
		twitter = getTwitterObject()
		
		timeline = twitter.GetUserTimeline({'screen_name': profile_name, 'count': 100})
		user = timeline[0]['user']
		context['description'] = user['description']
		context['following'] = user['friends_count']
		context['followers'] = user['followers_count']
		context['updates'] = user['statuses_count']
		
		context['image_url'] = user['profile_image_url']
		context['url'] = user['url']
		context['created'] = user['created_at']
		context['location'] = user['location']
		
		data = ""
		for entry in timeline:
			data += " %s" % entry['text']
		
		p = re.compile(r'[^a-zA-Z0-9@#_]') # Add foreign languages here
		data = p.sub(' ', data)
		data = remove_stopwords(data)
		data = data.lower()
		
		topics = {}
		mentions = {}
		hashtags = {}
		
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
		
		context['topics_cloud_html'] = get_cloud_html(topics)
		context['mentions_cloud_html'] = get_cloud_html(mentions)
		context['hashtags_cloud_html'] = get_cloud_html(hashtags)
		
		#context = {'profile_name': profile_name}
		render(self, "profile.html", context)

class Admin(webapp.RequestHandler):
		def get(self, action):
			if action == 'register':
				options = Option.all()
				options.filter('name >=', 'oauth-').filter('name <', 'oauth-' + u'\ufffd')
				options.fetch(1000)
				for option in options:
					option.delete()
				
				twitter = OAuthApi(consumer_key, consumer_secret)
				credentials = twitter.getRequestToken()
				self.response.out.write(twitter.getAuthorizationURL(credentials))
				
				# Save the tokens to the datastore for later authentication
				oauth_token = credentials['oauth_token']
				oauth_token_secret = credentials['oauth_token_secret']
				
				opt = Option(name='oauth-request-token', value=oauth_token)
				opt.put()
				opt = Option(name='oauth-request-token-secret', value=oauth_token_secret)
				opt.put()
				
			elif action == 'verify':
				twitter = OAuthApi(consumer_key, consumer_secret)
				oauth_verifier = self.request.get('oauth_verifier')
				
				options = Option.all()
				options.filter('name =', 'oauth-request-token')
				oauth_token = options.get()
				
				options = Option.all()
				options.filter('name =', 'oauth-request-token-secret')
				oauth_token_secret = options.get()
				
				credentials = {'oauth_token': oauth_token.value, 'oauth_token_secret': oauth_token_secret.value, 'oauth_callback_confirmed': 'true'}
				credentials = twitter.getAccessToken(credentials, oauth_verifier)
				
				access_token = Option(name='oauth-access-token', value=credentials['oauth_token'])
				access_token_secret = Option(name='oauth-access-token-secret', value=credentials['oauth_token_secret'])
				
				oauth_token.delete()
				oauth_token_secret.delete()
				access_token.put()
				access_token_secret.put()
				
				self.response.out.write("You are now registered as @%s!" % credentials['screen_name'])
			
			elif action == 'work':
				taskqueue.add(url='/admin/worker/', params={'task': 'geo'}, method='GET')
				self.response.out.write("Geo task added to queue")
			
			elif action == 'worker':
				query = Geo.all()
				query.filter('geo =', 'None')
				results = query.fetch(5)
				for result in results:
					form_fields = {'q': result.location.encode('utf-8'), 'output': 'csv', 'key': 'ABQIAAAAXG5dungCtctVf8ll0MRanhR9iirwL7nBc9d2R7_tFiOfa5aC4RSTKOF-7Bi7s8MaO5KAlewwElCpIA'}
					form_data = urllib.urlencode(form_fields)
					
					google_maps = urlfetch.fetch(url='http://maps.google.com/maps/geo?' + form_data)
					if google_maps.status_code == 200:
						status, n, lat, lon = google_maps.content.split(',')
						result.geo = "%s,%s" % (lat, lon)
						result.put()
						
					time.sleep(1)
					
			
def render(obj, tpl='default.html', context={}):
	obj.response.out.write(template.render('templates/' + tpl, context))
	
def rendertext(obj, text):
	obj.response.out.write(text)

class Option(db.Model):
	name = db.StringProperty(required=True)
	value = db.StringProperty()
	
class Geo(db.Model):
	location = db.StringProperty(required=True)
	geo = db.StringProperty(required=True, multiline=True)

def getTwitterObject():
	options = Option.all()
	options.filter('name =', 'oauth-access-token')
	access_token = options.get()

	options = Option.all()
	options.filter('name =', 'oauth-access-token-secret')
	access_token_secret = options.get()

	twitter = OAuthApi(consumer_key, consumer_secret, access_token.value, access_token_secret.value)
	return twitter
	
def remove_stopwords(text):
	from stopwords import stopwords
	words = text.split()
	clean = []
	for word in words:
		if not word.isdigit() and not word.lower() in stopwords:
			clean.append(word)
			
	return ' '.join(clean)
	
def get_cloud_html(words, url="http://search.twitter.com/search?q=%s"):
	min_font_size = 12
	max_font_size = 30
	
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
		
	step = (max_font_size - min_font_size) / spread
	
	result = []
	
	for word, c in words.items():
		if c > (min_output - 2):
			size = min_font_size + (c - minimum) * step
			result.append('<a style="font-size: %(size)spx" class="tag_cloud" href="%(url)s" title="\'%(word)s\' has been used %(count)s times">%(word)s</a>' % {'size': size, 'word': word, 'url': url % word, 'count': c})
			
	return ' '.join(result)

urls = [
	(r'/', Home),
	(r'/admin/(\w+)/?', Admin),
	(r'/ajax/(\w+)/?', Ajax),
	(r'/(\w+)/?', Profile),
]
application = webapp.WSGIApplication(urls, debug=True)

def main():
	run_wsgi_app(application)

if __name__ == '__main__':
	main()
