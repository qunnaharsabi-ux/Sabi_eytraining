const express = require('express');

const app = express();
const PORT = 8080;

// Home route
app.get('/', (req, res) => {
    res.send('<h1>Hello from AKS!</h1><p>Pod Name: ${process.env.HOSTNAME}</p>');
});

// Start server
app.listen(PORT, () => {
    console.log(`Server is running on ${PORT}`);
});
