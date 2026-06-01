// Paste this in browser console on any polymarket.com page (with VPN).
// It fetches live BTC Up/Down markets and prints their condition IDs.

fetch('https://gamma-api.polymarket.com/markets?active=true&closed=false&limit=200')
  .then(r => r.json())
  .then(markets => {
    const btc = markets.filter(m =>
      /(bitcoin|btc)/i.test(m.question) &&
      /(higher|lower|up|down|\$)/i.test(m.question)
    );
    if (!btc.length) {
      console.log('No BTC Up/Down markets found. Try without filters:');
      markets.slice(0, 5).forEach(m => console.log(m.conditionId, '|', m.question));
      return;
    }
    console.log(`Found ${btc.length} BTC Up/Down market(s):\n`);
    btc.forEach(m => console.log(m.conditionId, '|', m.question));
    console.log('\n--- Copy any conditionId above ---');
    console.log('Then run:');
    console.log(`PYTHONPATH=. uv run python strategies/crypto_updown/latency_probe.py --market ${btc[0].conditionId} --duration 300`);
  })
  .catch(e => console.error('Error:', e));
