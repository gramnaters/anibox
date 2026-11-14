async function inspectAbyss() {
  const embed = 'https://tooniboy.xyz/view-movie/?id=1268';
  const r = await fetch(embed);
  const html = await r.text();
  const m = html.match(/const\s+datas\s*=\s*['"]([^'"]+)['"]/i);
  if (!m) return console.log('no datas');
  const dec = await fetch('https://enc-dec.app/api/dec-abyss', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Referer': 'https://playhydrax.com/' },
    body: JSON.stringify({ text: m[1] })
  });
  const json = await dec.json();
  console.log(JSON.stringify(json, null, 2));
}
inspectAbyss();
