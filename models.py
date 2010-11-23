from google.appengine.ext import db

# The Option model, used to store OAuth tokens and other settings
class Option(db.Model):
	name = db.StringProperty(required=True)
	value = db.StringProperty()
	
# Used to store the geo locations to geo-points relations
class Geo(db.Model):
	location = db.StringProperty(required=True)
	geo = db.StringProperty(required=True, multiline=True)
	
# Used to store recent queries in the datastore
class Recent(db.Model):
	screen_name = db.StringProperty(required=True)
	profile_image_url = db.StringProperty(required=True)
	published = db.DateTimeProperty(required=True, auto_now=True, auto_now_add=True)
