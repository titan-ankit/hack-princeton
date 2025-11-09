import { getMessageByErrorCode } from "@/lib/errors";
import { expect, test } from "../fixtures";
import { generateRandomTestUser } from "../helpers";
import { AuthPage } from "../pages/auth";
import { ChatPage } from "../pages/chat";

test.describe.serial("Unauthenticated Session", () => {
  test("Loads without creating a guest session", async ({ page }) => {
    const response = await page.goto("/");

    if (!response) {
      throw new Error("Failed to load page");
    }

    let request = response.request();

    const chain: string[] = [];

    while (request) {
      chain.unshift(request.url());
      request = request.redirectedFrom();
    }

    expect(chain).toEqual(["http://localhost:3000/"]);
  });

  test("Shows login option in sidebar for unauthenticated users", async ({
    page,
  }) => {
    await page.goto("/");

    const sidebarToggleButton = page.getByTestId("sidebar-toggle-button");
    await sidebarToggleButton.click();

    const userNavButton = page.getByTestId("user-nav-button");
    await expect(userNavButton).toBeVisible();
    await expect(userNavButton).toContainText("Log in");
  });

  test("Allows navigating to /login when unauthenticated", async ({ page }) => {
    await page.goto("/login");
    await page.waitForURL("/login");
    await expect(page).toHaveURL("/login");
  });

  test("Allows navigating to /register when unauthenticated", async ({
    page,
  }) => {
    await page.goto("/register");
    await page.waitForURL("/register");
    await expect(page).toHaveURL("/register");
  });
});

test.describe
  .serial("Login and Registration", () => {
    let authPage: AuthPage;

    const testUser = generateRandomTestUser();

    test.beforeEach(({ page }) => {
      authPage = new AuthPage(page);
    });

    test("Register new account", async () => {
      await authPage.register(testUser.email, testUser.password);
      await authPage.expectToastToContain("Account created successfully!");
    });

    test("Register new account with existing email", async () => {
      await authPage.register(testUser.email, testUser.password);
      await authPage.expectToastToContain("Account already exists!");
    });

    test("Log into account that exists", async ({ page }) => {
      await authPage.login(testUser.email, testUser.password);

      await page.waitForURL("/");
      await expect(page.getByPlaceholder("Send a message...")).toBeVisible();
    });

    test("Display user email in user menu", async ({ page }) => {
      await authPage.login(testUser.email, testUser.password);

      await page.waitForURL("/");
      await expect(page.getByPlaceholder("Send a message...")).toBeVisible();

      const userEmail = await page.getByTestId("user-email");
      await expect(userEmail).toHaveText(testUser.email);
    });

    test("Log out as non-guest user", async () => {
      await authPage.logout(testUser.email, testUser.password);
    });

    test("Log out is available for non-guest users", async ({ page }) => {
      await authPage.login(testUser.email, testUser.password);
      await page.waitForURL("/");

      authPage.openSidebar();

      const userNavButton = page.getByTestId("user-nav-button");
      await expect(userNavButton).toBeVisible();

      await userNavButton.click();
      const userNavMenu = page.getByTestId("user-nav-menu");
      await expect(userNavMenu).toBeVisible();

      const authMenuItem = page.getByTestId("user-nav-item-auth");
      await expect(authMenuItem).toContainText("Sign out");
    });

    test("Do not navigate to /register for non-guest users", async ({
      page,
    }) => {
      await authPage.login(testUser.email, testUser.password);
      await page.waitForURL("/");

      await page.goto("/register");
      await expect(page).toHaveURL("/");
    });

    test("Do not navigate to /login for non-guest users", async ({ page }) => {
      await authPage.login(testUser.email, testUser.password);
      await page.waitForURL("/");

      await page.goto("/login");
      await expect(page).toHaveURL("/");
    });
  });

test.describe("Entitlements", () => {
  let chatPage: ChatPage;

  test.beforeEach(({ page }) => {
    chatPage = new ChatPage(page);
  });

  test("Guest user cannot send more than 20 messages/day", async () => {
    test.fixme();
    await chatPage.createNewChat();

    for (let i = 0; i <= 20; i++) {
      await chatPage.sendUserMessage("Why is the sky blue?");
      await chatPage.isGenerationComplete();
    }

    await chatPage.sendUserMessage("Why is the sky blue?");
    await chatPage.expectToastToContain(
      getMessageByErrorCode("rate_limit:chat")
    );
  });
});
