import React, { useEffect, useState } from 'react';
import axios from 'axios';

const API_BASE = "http://192.168.1.11:5000";

function App() {
  const [collections, setCollections] = useState([]);
  const [selectedCollection, setSelectedCollection] = useState(null);
  const [status, setStatus] = useState("");

  useEffect(() => {
    axios.get(`${API_BASE}/collections`)
      .then(res => setCollections(res.data))
      .catch(err => setStatus("Failed to fetch collections"));
  }, []);

  const setCollection = (collection) => {
    axios.post(`${API_BASE}/set_collection`, { collection })
      .then(() => {
        setSelectedCollection(collection);
        setStatus(`🎯 Set to ${collection}`);
      })
      .catch(() => setStatus("❌ Error setting collection"));
  };

  const sendCommand = (cmd) => {
    axios.post(`${API_BASE}/${cmd}`)
      .then(() => setStatus(`${cmd.toUpperCase()} sent`))
      .catch(() => setStatus(`❌ Error sending ${cmd}`));
  };

  return (
    <div style={{ padding: '1rem', fontFamily: 'sans-serif', maxWidth: 600, margin: 'auto', backgroundColor: '#000', color: '#ff0080' }}>
      <img src="/540x405.png" alt="DBTV Logo" style={{ width: '200px', marginBottom: '1rem' }} />
      <h1>📺 DBTV Remote</h1>
      <div>
        <h2>Collections</h2>
        {collections.map(col => (
          <button
            key={col}
            onClick={() => setCollection(col)}
            style={{
              margin: 4,
              padding: 10,
              background: col === selectedCollection ? '#ff0080' : '#eee',
              color: col === selectedCollection ? '#000' : '#ff0080',
              border: 'none',
              cursor: 'pointer'
            }}
          >
            {col}
          </button>
        ))}
      </div>
      <hr />
      <div>
        <h2>Controls</h2>
        <button onClick={() => sendCommand('play')} style={{ color: '#ff0080', background: 'transparent', border: '1px solid #ff0080', marginRight: 8, padding: '6px 12px', cursor: 'pointer' }}>▶️ Play</button>
        <button onClick={() => sendCommand('pause')} style={{ color: '#ff0080', background: 'transparent', border: '1px solid #ff0080', marginRight: 8, padding: '6px 12px', cursor: 'pointer' }}>⏸ Pause</button>
        <button onClick={() => sendCommand('restart')} style={{ color: '#ff0080', background: 'transparent', border: '1px solid #ff0080', padding: '6px 12px', cursor: 'pointer' }}>🔁 Restart</button>
      </div>
      <p>{status}</p>
    </div>
  );
}

export default App;