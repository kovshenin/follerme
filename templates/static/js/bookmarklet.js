var fmurl = window.location.href; 
var fmregex = /^http:\/\/twitter.com/i;

var request = fmurl.match(fmregex);

if (request != null)
{
	var script = document.createElement('script');
	script.type = 'text/javascript';
	script.src = 'http://jqueryjs.googlecode.com/files/jquery-1.3.2.min.js';
	document.getElementsByTagName('head')[0].appendChild(script);
	
	jQuery.each(jQuery("a.screen-name"), function() {
		jQuery(this).after("<a style=\"margin-right: 5px;\" href=\"http://foller.me/" + jQuery(this).html() + "\"><img src=\"http://foller.me.local/home/s3/images/favicon.ico\" /></a> ");
	});
	
	jQuery.each(jQuery("a.tweet-url.username"), function() {
		jQuery(this).after("<a style=\"margin-right: 3px;\" href=\"http://foller.me" + "\"><img src=\"http://foller.me.local/home/s3/images/favicon.ico\" /></a> ");
	});
		
	//request = request[1];
	//document.body.innerHTML = document.body.innerHTML.replace(/<a\b[^>]*>(.*?)<\/a>/i,'');
	//alert("one");
	//window.location.href = "http://foller.me/"+username;
}
else
{
	alert("aaaaaaaffaaThis is not a Twitter profile page, is it?");
}