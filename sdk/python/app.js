// Simple Node.js Hello World Application
console.log("Hello, World!");

// Optional: Create a simple HTTP server
const http = require('http');

const server = http.createServer((req, res) => {
    res.writeHead(200, { 'Content-Type': 'text/plain' });
    res.end('Hello, World!\n');
});

const PORT = process.env.PORT || 3000;

server.listen(PORT, () => {
    console.log(`Server running at http://localhost:null/`);
});
