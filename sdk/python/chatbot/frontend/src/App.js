import React, { useState } from 'react';
import './App.css';
import ChatInterface from './components/ChatInterface';
import ApiKeyInput from './components/ApiKeyInput';

function App() {
  const [apiKey, setApiKey] = useState('');
  const [isApiKeySet, setIsApiKeySet] = useState(false);

  const handleApiKeySubmit = (key) => {
    setApiKey(key);
    setIsApiKeySet(true);
  };

  const handleApiKeyReset = () => {
    setApiKey('');
    setIsApiKeySet(false);
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>🤖 OpenAI Chatbot</h1>
        {isApiKeySet && (
          <button className="reset-key-btn" onClick={handleApiKeyReset}>
            Change API Key
          </button>
        )}
      </header>
      
      <main className="App-main">
        {!isApiKeySet ? (
          <ApiKeyInput onApiKeySubmit={handleApiKeySubmit} />
        ) : (
          <ChatInterface apiKey={apiKey} />
        )}
      </main>
    </div>
  );
}

export default App;