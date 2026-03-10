test('create note', async () => {
  await request(app).post('/api/notes');
});

test('update note', async () => {
  await request(app).put('/api/notes/42');
});
