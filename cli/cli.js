#!/usr/bin/env node

// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.


const { spawnSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const platform = process.platform;
const binaryName = platform === 'win32' ? 'agentspan.exe' : 'agentspan';
const binaryPath = path.join(__dirname, 'bin', binaryName);

// Check if binary exists
if (!fs.existsSync(binaryPath)) {
  console.error('Error: Binary not found. Please reinstall the package.');
  console.error('Run: npm uninstall -g @agentspan-ai/agentspan && npm install -g @agentspan-ai/agentspan');
  process.exit(1);
}

// Execute the binary with all arguments
const result = spawnSync(binaryPath, process.argv.slice(2), {
  stdio: 'inherit',
  shell: false
});

process.exit(result.status);
