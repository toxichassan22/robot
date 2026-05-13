/** @type {import('jest').Config} */
module.exports = {
  projects: [
    {
      displayName: "client",
      testEnvironment: "jsdom",
      testMatch: ["<rootDir>/frontend/src/__tests__/**/*.test.ts?(x)"],
      setupFiles: ["<rootDir>/frontend/src/__tests__/setup.ts"],
      moduleNameMapper: {
        "^(\\.{1,2}/.*)\\.js$": "$1",
      },
      transform: {
        "^.+\\.(t|j)sx?$": ["ts-jest", { useESM: true, tsconfig: "<rootDir>/tsconfig.json" }],
      },
      extensionsToTreatAsEsm: [".ts", ".tsx"],
    },
    {
      displayName: "server",
      testEnvironment: "node",
      testMatch: ["<rootDir>/backend/api/__tests__/**/*.test.ts"],
      moduleNameMapper: {
        "^(\\.{1,2}/.*)\\.js$": "$1",
      },
      transform: {
        "^.+\\.(t|j)sx?$": ["ts-jest", { useESM: true, tsconfig: "<rootDir>/tsconfig.json" }],
      },
      extensionsToTreatAsEsm: [".ts"],
    },
  ],
};
