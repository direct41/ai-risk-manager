test('covers event consumer and http ingress', async () => {
  emitEvent('note.created');
  await client.post('/api/health');
});
