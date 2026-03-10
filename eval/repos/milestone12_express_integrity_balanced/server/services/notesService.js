function mapRow(row) {
  return { id: row.id, is_archived: row.is_archived };
}

async function createNote(input) {
  const tagsCsv = String(input.tags || '')
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean)
    .join(',');
  await db.run(
    `INSERT INTO notes (title, content, tags) VALUES (?, ?, ?)`,
    [input.title, input.content, tagsCsv],
  );
}

async function archiveNote(userId, id) {
  await db.run(`UPDATE notes SET is_archived = 1 WHERE id = ? AND user_id = ?`, [id, userId]);
}

async function autosaveNote(userId, id, input) {
  const clientUpdatedAt = input.updatedAt;
  await db.run(
    `UPDATE notes SET content = ?, updated_at = ? WHERE id = ? AND user_id = ? AND updated_at = ?`,
    [input.content, new Date().toISOString(), id, userId, clientUpdatedAt],
  );
}

module.exports = {
  mapRow,
  createNote,
  archiveNote,
  autosaveNote,
};
