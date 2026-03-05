const express = require('express');

const app = express();
app.use(express.json());

app.post('/internal/reset', (_req, res) => {
  res.json({ ok: true });
});

app.use('/api', (req, res, next) => {
  const token = req.header('x-session-token');
  if (token !== 'demo-token') {
    return res.status(401).json({ error: 'Unauthorized' });
  }
  next();
});

app.post('/api/notes', (_req, res) => {
  res.status(201).json({ ok: true });
});

module.exports = app;
