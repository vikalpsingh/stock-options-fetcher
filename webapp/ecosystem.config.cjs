module.exports = {
  apps: [
    {
      name: "ujjain-kumbh-guide",
      script: "node_modules/next/dist/bin/next",
      args: "start -p 3000",
      cwd: __dirname,
      instances: 1,
      exec_mode: "fork",
      autorestart: true,
      max_memory_restart: "750M",
      env: {
        NODE_ENV: "production",
      },
    },
  ],
};
