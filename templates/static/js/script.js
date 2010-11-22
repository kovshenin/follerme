var map = null;

jQuery(document).ready(function(){
	jQuery(".twitter_input").focus(function(){
		if (this.value == "type in a Twitter name")
			this.value = "";
	});
	
	jQuery(".twitter_input").blur(function(){
		if (this.value == "")
			this.value = "type in a Twitter name";
	});
	
	jQuery(".activate").focus();
});

/* Fire an AJAX call to request a map */
function getMap(username) {
	jQuery.post('/ajax/gmap/', 'profile=' + username, function(data, textStatus) {
		jQuery('.gmaps').html(data);
		jQuery('#map_container').fadeTo(2000, 1);
	});
}

/* Use this function to generate markers */
function showPoint(lat, lng, html, self) { 
    point = new GLatLng(lat, lng);
    var marker = createMarker(point, html, self); 
    map.addOverlay(marker); 
}

/* And this function is the one that actually creates the markers on the map */
function createMarker(point, html, self) {
	var dir = (self) ? "self/" : "";
	// Create a lettered icon for this point using our icon class
	var myIcon = new GIcon();
	myIcon.image = '/static/images/gmaps/' + dir + 'image.png';
	myIcon.printImage = '/static/images/gmaps/' + dir + 'printImage.gif';
	myIcon.mozPrintImage = '/static/images/gmaps/' + dir + 'mozPrintImage.gif';
	myIcon.iconSize = new GSize(25,28);
	myIcon.shadow = '/static/images/gmaps/' + dir + 'shadow.png';
	myIcon.transparent = '/static/images/gmaps/' + dir + 'transparent.png';
	myIcon.shadowSize = new GSize(39,28);
	myIcon.printShadow = '/static/images/gmaps/' + dir + 'printShadow.gif';
	myIcon.iconAnchor = new GPoint(13,28);
	myIcon.infoWindowAnchor = new GPoint(13,0);
	myIcon.imageMap = [22,0,22,1,23,2,23,3,23,4,23,5,23,6,23,7,23,8,23,9,23,10,23,11,23,12,23,13,23,14,23,15,23,16,23,17,23,18,22,19,21,20,12,21,11,22,10,23,9,24,8,25,23,26,22,27,2,27,1,26,8,25,8,24,8,23,9,22,9,21,2,20,0,19,0,18,0,17,0,16,0,15,0,14,0,13,0,12,0,11,0,10,0,9,0,8,0,7,0,6,0,5,0,4,0,3,0,2,0,1,1,0];
	
	// Set up our GMarkerOptions object
	markerOptions = { icon:myIcon };
	var marker = new GMarker(point, markerOptions);
	
	GEvent.addListener(marker, "click", function() {
	marker.openInfoWindowHtml(html);
	});
	
	return marker;
}
