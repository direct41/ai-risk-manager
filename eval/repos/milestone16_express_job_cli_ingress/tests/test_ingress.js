test('covers job cli and http ingress', async () => {
  runJob('sync-notes');
  runCli('sync-notes');
  await client.post('/api/health');
});
