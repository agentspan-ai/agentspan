/**
 * Real-server e2e coverage for the Skills browser.
 *
 * This test registers a real skill package through the runtime API, then uses
 * the browser UI to list it, open its detail page, and preview packaged files.
 */
import { expect, request, test } from "@playwright/test";
import { Buffer } from "node:buffer";

type SkillFiles = Record<string, string>;

const SERVER_URL =
  process.env.AGENTSPAN_UI_E2E_SERVER_URL ||
  process.env.VITE_WF_SERVER ||
  "http://127.0.0.1:6767";

const FORCE_REAL_SERVER = process.env.AGENTSPAN_UI_E2E_REAL === "1";

function crc32(data: Buffer): number {
  let crc = 0xffffffff;
  for (const byte of data) {
    crc ^= byte;
    for (let i = 0; i < 8; i += 1) {
      const mask = -(crc & 1);
      crc = (crc >>> 1) ^ (0xedb88320 & mask);
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function dosDateTime() {
  return {
    time: 0,
    date: (45 << 9) | (1 << 5) | 1, // 2025-01-01
  };
}

function createZip(files: SkillFiles): Buffer {
  const fileRecords: Array<{
    name: Buffer;
    data: Buffer;
    crc: number;
    offset: number;
  }> = [];
  const localParts: Buffer[] = [];
  let offset = 0;
  const { time, date } = dosDateTime();

  for (const [path, content] of Object.entries(files)) {
    const name = Buffer.from(path, "utf8");
    const data = Buffer.from(content, "utf8");
    const crc = crc32(data);
    const header = Buffer.alloc(30);
    header.writeUInt32LE(0x04034b50, 0);
    header.writeUInt16LE(20, 4);
    header.writeUInt16LE(0x0800, 6);
    header.writeUInt16LE(0, 8);
    header.writeUInt16LE(time, 10);
    header.writeUInt16LE(date, 12);
    header.writeUInt32LE(crc, 14);
    header.writeUInt32LE(data.length, 18);
    header.writeUInt32LE(data.length, 22);
    header.writeUInt16LE(name.length, 26);
    header.writeUInt16LE(0, 28);

    fileRecords.push({ name, data, crc, offset });
    localParts.push(header, name, data);
    offset += header.length + name.length + data.length;
  }

  const centralParts: Buffer[] = [];
  let centralSize = 0;
  for (const record of fileRecords) {
    const header = Buffer.alloc(46);
    header.writeUInt32LE(0x02014b50, 0);
    header.writeUInt16LE(20, 4);
    header.writeUInt16LE(20, 6);
    header.writeUInt16LE(0x0800, 8);
    header.writeUInt16LE(0, 10);
    header.writeUInt16LE(time, 12);
    header.writeUInt16LE(date, 14);
    header.writeUInt32LE(record.crc, 16);
    header.writeUInt32LE(record.data.length, 20);
    header.writeUInt32LE(record.data.length, 24);
    header.writeUInt16LE(record.name.length, 28);
    header.writeUInt16LE(0, 30);
    header.writeUInt16LE(0, 32);
    header.writeUInt16LE(0, 34);
    header.writeUInt16LE(0, 36);
    header.writeUInt32LE(0, 38);
    header.writeUInt32LE(record.offset, 42);
    centralParts.push(header, record.name);
    centralSize += header.length + record.name.length;
  }

  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(0, 4);
  end.writeUInt16LE(0, 6);
  end.writeUInt16LE(fileRecords.length, 8);
  end.writeUInt16LE(fileRecords.length, 10);
  end.writeUInt32LE(centralSize, 12);
  end.writeUInt32LE(offset, 16);
  end.writeUInt16LE(0, 20);

  return Buffer.concat([...localParts, ...centralParts, end]);
}

async function requireSkillsApi() {
  const api = await request.newContext({ baseURL: SERVER_URL });
  const response = await api
    .get("/api/skills", { timeout: 5000 })
    .catch(() => null);
  if (!response?.ok()) {
    await api.dispose();
    if (FORCE_REAL_SERVER) {
      throw new Error(
        `Skills API is not available at ${SERVER_URL}/api/skills`,
      );
    }
    test.skip(
      true,
      `Skills API is not available at ${SERVER_URL}; skipping real integration test.`,
    );
  }
  return api;
}

test.describe("Skills UI", () => {
  test("lists a registered skill and previews package files", async ({
    page,
  }) => {
    const api = await requireSkillsApi();
    const suffix = Date.now().toString(36);
    const skillName = `ui_skill_${suffix}`;
    const version = `v-${suffix}`;
    const files: SkillFiles = {
      "SKILL.md": `---
name: ${skillName}
description: UI browse fixture
---
## Workflow
Call the ${skillName}__echo_args tool and return its output.
`,
      "alpha-agent.md": "# Alpha Agent\nAnalyze the request.\n",
      "references/guide.md":
        "# UI_GUIDE\nThis reference was loaded from the registered package.\n",
      "scripts/echo_args.py": `#!/usr/bin/env python3
import sys
args = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "no-args"
print(f"UI_SKILL_ECHO:{args}")
`,
    };
    const packageBytes = createZip(files);
    const manifest = {
      name: skillName,
      version,
      description: "UI browse fixture",
      model: "openai/gpt-4o-mini",
    };

    try {
      const register = await api.post("/api/skills/register", {
        multipart: {
          manifest: JSON.stringify(manifest),
          package: {
            name: "skill.zip",
            mimeType: "application/zip",
            buffer: packageBytes,
          },
        },
      });
      expect(register.ok(), await register.text()).toBe(true);

      await page.goto("/skills");
      await expect(page).toHaveTitle(/Skills/);
      await expect(page.getByRole("link", { name: skillName })).toBeVisible();
      await expect(page.getByText("UI browse fixture")).toBeVisible();
      const contentsCell = page.locator(`#cell-contents-${skillName}`);
      await expect(contentsCell.getByText("4 files")).toBeVisible();
      await expect(contentsCell.getByText("1 agents")).toBeVisible();
      await expect(contentsCell.getByText("1 scripts")).toBeVisible();
      await expect(contentsCell.getByText("1 resources")).toBeVisible();

      await page.getByRole("link", { name: skillName }).click();
      await expect(page).toHaveTitle(new RegExp(`${skillName} Skill`));
      await expect(page.getByText(`Version ${version}`)).toBeVisible();
      await expect(page.locator("pre")).toContainText("UI browse fixture");

      await page.getByRole("button", { name: "references/guide.md" }).click();
      await expect(page.locator("pre")).toContainText("UI_GUIDE");

      await page.getByRole("button", { name: "scripts/echo_args.py" }).click();
      await expect(page.locator("pre")).toContainText("UI_SKILL_ECHO");
    } finally {
      await api.delete(
        `/api/skills/${encodeURIComponent(skillName)}/versions/${encodeURIComponent(version)}`,
      );
      await api.dispose();
    }
  });
});
