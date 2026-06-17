// Gandalf landing worker: static assets plus a couple of friendly routes.
export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // `curl -fsSL https://gandalf.sh/install | sh`
    if (url.pathname === "/install" || url.pathname === "/install.sh") {
      return Response.redirect(
        "https://raw.githubusercontent.com/mannanj/skillguard/main/install.sh",
        302,
      );
    }

    // Canonical host: collapse www → apex
    if (url.hostname === "www.gandalf.sh") {
      url.hostname = "gandalf.sh";
      return Response.redirect(url.toString(), 301);
    }

    return env.ASSETS.fetch(request);
  },
};
