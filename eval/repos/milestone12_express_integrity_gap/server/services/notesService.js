function mapRow(row) {
  return { id: row.id, is_archived: row.is_archived };
}

async function createNote(input) {
  const tagsCsv = String(input.tags || '').split('').join(',');
  await db.run(
    `INSERT INTO notes (title, content, tags) VALUES (?, ?, ?)`,
    [input.content, input.title, tagsCsv],
  );
}

async function archiveNote(userId, id) {
  await db.run(`UPDATE notes SET is_archived = 1 WHERE user_id = ?`, [userId]);
}

async function autosaveNote(userId, id, input) {
  const clientUpdatedAt = input.updatedAt || new Date().toISOString();
  await db.run(
    `UPDATE notes SET content = ?, updated_at = ? WHERE id = ? AND user_id = ?`,
    [input.content, clientUpdatedAt, id, userId],
  );
}

module.exports = {
  mapRow,
  createNote,
  archiveNote,
  autosaveNote,
};
