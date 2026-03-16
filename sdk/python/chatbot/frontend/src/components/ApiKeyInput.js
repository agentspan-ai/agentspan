import React, { useState } from 'react';
import './ApiKeyInput.css';

const ApiKeyInput = ({ onApiKeySubmit }) => {
  const [apiKey, setApiKey] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    
    if (!apiKey.trim()) {
      setError('Please enter your OpenAI API key');
      return;
    }

    if (!apiKey.startsWith('sk-')) {
      setError('OpenAI API keys should start with "sk-"');
      return;
    }

    setError('');
    onApiKeySubmit(apiKey.trim());
  };

  return (
    <div className="api-key-container">
      <div className="api-key-card">
        <h2>🔑 Enter Your OpenAI API Key</h2>
        <p className="api-key-description">
          To use this chatbot, you need to provide your OpenAI API key. 
          Your key will only be stored locally in your browser session.
        </p>
        
        <form onSubmit={handleSubmit} className="api-key-form">
          <div className="input-group">
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="sk-..."
              className="api-key-input"
            />
            <button type="submit" className="submit-btn">
              Start Chatting
            </button>
          </div>
          {error && <div className="error-message">{error}</div>}
        </form>

        <div className="api-key-info">
          <h3>How to get your API key:</h3>
          <ol>
            <li>Go to <a href="https://platform.openai.com/api-keys" target="_blank" rel="noopener noreferrer">OpenAI API Keys</a></li>
            <li>Sign in to your OpenAI account</li>
            <li>Click "Create new secret key"</li>
            <li>Copy the key and paste it above</li>
          </ol>
        </div>
      </div>
    </div>
  );
};

export default ApiKeyInput;