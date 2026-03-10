const express = require('express');

const app = express();

queue.process('sync-notes', syncNotesJob);
program.command('sync-notes');

app.use('/api', (req, res, next) => {
  const token = req.header('x-session-token');
  if (token !== 'demo') {
    return res.status(401).json({ error: 'Unauthorized' });
  }
  next();
});

app.post('/api/health', (_req, res) => res.json({ ok: true }));

module.exports = { app };
