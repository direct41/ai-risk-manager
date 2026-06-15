import { issueRecoveryToken } from "../../server/services/accountRecovery.js";

test("issues an account recovery token", () => {
  expect(issueRecoveryToken("user-1")).toEqual({
    userId: "user-1",
    status: "issued",
  });
});
