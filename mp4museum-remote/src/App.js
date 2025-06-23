import React, { useEffect, useState } from 'react';
import axios from 'axios';

const API_BASE = "http://192.168.1.170:5000";

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
    <div style={{ padding: '1rem', fontFamily: 'sans-serif', maxWidth: 600, margin: 'auto' }}>
      <h1>🎛 MP4Museum Remote</h1>
      <div>
        <h2>Collections</h2>
        {collections.map(col => (
          <button
            key={col}
            onClick={() => setCollection(col)}
            style={{
              margin: 4,
              padding: 10,
              background: col === selectedCollection ? '#00d084' : '#eee'
            }}
          >
            {col}
          </button>
        ))}
      </div>
      <hr />
      <div>
        <h2>Controls</h2>
        <button onClick={() => sendCommand('play')}>▶️ Play</button>
        <button onClick={() => sendCommand('pause')}>⏸ Pause</button>
        <button onClick={() => sendCommand('restart')}>🔁 Restart</button>
      </div>
      <p>{status}</p>
    </div>
  );
}

export default App;