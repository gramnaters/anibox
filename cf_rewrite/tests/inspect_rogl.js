async function testImdb() {
  const res = await fetch('https://rozgarlelo.modiplay.xyz/embed/imdb/movie?id=tt15239678');
  console.log('IMDb movie status:', res.status);
  const text = await res.text();
  const ifm = text.match(/<iframe[^>]+src="([^"]+)"/i);
  console.log('iframe:', ifm ? ifm[1] : 'none');
}
testImdb();
