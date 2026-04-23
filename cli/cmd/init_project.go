// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/fatih/color"
	"github.com/spf13/cobra"
	"gopkg.in/yaml.v3"
)

var (
	initProjectLanguage string
	initProjectModel    string
	initProjectForce    bool
)

var initProjectCmd = &cobra.Command{
	Use:   "init-project <agent-name>",
	Short: "Create a new deployable agent project",
	Long: `Generate a complete agent project with source code, dependencies, and config.

Creates a directory structure ready for both:
- Running on the AgentSpan runtime (agent config)
- Deploying via 'agent deploy' (source code)

Supported languages: python, typescript, java`,
	Example: `  # Create a Python agent project
  agentspan agent init-project my-agent --language python

  # Create a TypeScript agent project
  agentspan agent init-project my-agent --language typescript

  # Create with a specific model
  agentspan agent init-project my-agent --language python --model anthropic/claude-sonnet-4-20250514`,
	Args: cobra.ExactArgs(1),
	RunE: runInitProject,
}

func init() {
	initProjectCmd.Flags().StringVarP(&initProjectLanguage, "language", "l", "python", "Language: python, typescript, java")
	initProjectCmd.Flags().StringVarP(&initProjectModel, "model", "m", "openai/gpt-4o", "LLM model")
	initProjectCmd.Flags().BoolVarP(&initProjectForce, "force", "f", false, "Overwrite existing directory")
	agentCmd.AddCommand(initProjectCmd)
}

func runInitProject(cmd *cobra.Command, args []string) error {
	name := args[0]

	// Validate language
	switch initProjectLanguage {
	case "python", "typescript", "java":
		// OK
	default:
		return fmt.Errorf("unsupported language: %s (use python, typescript, or java)", initProjectLanguage)
	}

	// Check if directory exists
	if _, err := os.Stat(name); err == nil {
		if !initProjectForce {
			return fmt.Errorf("directory %s already exists (use --force to overwrite)", name)
		}
	}

	// Create project directory
	if err := os.MkdirAll(name, 0755); err != nil {
		return fmt.Errorf("create directory: %w", err)
	}

	// Create .agentspan directory
	agentspanDir := filepath.Join(name, ".agentspan")
	if err := os.MkdirAll(agentspanDir, 0755); err != nil {
		return fmt.Errorf("create .agentspan directory: %w", err)
	}

	// Generate files based on language
	var files map[string]string
	switch initProjectLanguage {
	case "python":
		files = generatePythonProject(name, initProjectModel)
	case "typescript":
		files = generateTypeScriptProject(name, initProjectModel)
	case "java":
		files = generateJavaProject(name, initProjectModel)
	}

	// Write all files
	for filename, content := range files {
		path := filepath.Join(name, filename)

		// Create parent directories if needed
		dir := filepath.Dir(path)
		if err := os.MkdirAll(dir, 0755); err != nil {
			return fmt.Errorf("create directory %s: %w", dir, err)
		}

		if err := os.WriteFile(path, []byte(content), 0644); err != nil {
			return fmt.Errorf("write %s: %w", filename, err)
		}
	}

	// Create deploy.lock
	deployLock := map[string]interface{}{
		"name":            name,
		"current_version": "0.0.0",
		"language":        initProjectLanguage,
		"entry_point":     getEntryPoint(initProjectLanguage),
		"runtime_version": getRuntimeVersion(initProjectLanguage),
	}
	lockData, _ := marshalJSON(deployLock)
	lockPath := filepath.Join(agentspanDir, "deploy.lock")
	if err := os.WriteFile(lockPath, lockData, 0644); err != nil {
		return fmt.Errorf("write deploy.lock: %w", err)
	}

	// Print success message
	color.Green("Created agent project: %s/", name)
	fmt.Println()
	fmt.Println("Project structure:")
	printProjectTree(name, initProjectLanguage)
	fmt.Println()
	fmt.Println("Next steps:")
	fmt.Printf("  cd %s\n", name)

	switch initProjectLanguage {
	case "python":
		fmt.Println("  pip install -r requirements.txt")
	case "typescript":
		fmt.Println("  npm install")
	case "java":
		fmt.Println("  mvn package")
	}

	fmt.Println()
	fmt.Printf("  # Run locally\n")
	fmt.Printf("  agentspan agent run --config %s.yaml \"Hello!\"\n", name)
	fmt.Println()
	fmt.Printf("  # Deploy to runtime\n")
	fmt.Printf("  agentspan agent deploy --name %s\n", name)

	return nil
}

func getEntryPoint(language string) string {
	switch language {
	case "python":
		return "main.py"
	case "typescript":
		return "src/index.ts"
	case "java":
		return "src/main/java/Agent.java"
	default:
		return "main"
	}
}

func getRuntimeVersion(language string) string {
	switch language {
	case "python":
		return "3.11"
	case "typescript":
		return "20"
	case "java":
		return "21"
	default:
		return ""
	}
}

func printProjectTree(name, language string) {
	fmt.Printf("  %s/\n", name)
	fmt.Println("  ├── .agentspan/")
	fmt.Println("  │   └── deploy.lock")
	fmt.Printf("  ├── %s.yaml          # Agent config\n", name)

	switch language {
	case "python":
		fmt.Println("  ├── main.py             # Entry point")
		fmt.Println("  ├── requirements.txt    # Dependencies")
		fmt.Println("  └── README.md")
	case "typescript":
		fmt.Println("  ├── src/")
		fmt.Println("  │   └── index.ts        # Entry point")
		fmt.Println("  ├── package.json        # Dependencies")
		fmt.Println("  ├── tsconfig.json       # TypeScript config")
		fmt.Println("  └── README.md")
	case "java":
		fmt.Println("  ├── src/main/java/")
		fmt.Println("  │   └── Agent.java      # Entry point")
		fmt.Println("  ├── pom.xml             # Maven config")
		fmt.Println("  └── README.md")
	}
}

func generatePythonProject(name, model string) map[string]string {
	// Agent config YAML
	agentConfig := map[string]interface{}{
		"name":         name,
		"description":  fmt.Sprintf("%s agent", name),
		"model":        model,
		"instructions": fmt.Sprintf("You are %s, a helpful AI assistant.", name),
		"maxTurns":     25,
		"tools":        []interface{}{},
	}
	configYAML, _ := yaml.Marshal(agentConfig)

	return map[string]string{
		fmt.Sprintf("%s.yaml", name): string(configYAML),

		"main.py": fmt.Sprintf(`#!/usr/bin/env python3
"""
%s - AgentSpan Agent

This agent can be run in two modes:
1. Via AgentSpan runtime: agentspan agent run --config %s.yaml "prompt"
2. Deployed to Kubernetes: agentspan agent deploy --name %s
"""

import os
import time
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%%(name)s] %%(message)s'
)
logger = logging.getLogger(os.getenv('AGENT_NAME', '%s'))


def main():
    """Main entry point for the deployed agent."""
    agent_name = os.getenv('AGENT_NAME', '%s')
    agent_version = os.getenv('AGENT_VERSION', 'dev')
    deploy_id = os.getenv('DEPLOY_ID', 'local')

    logger.info(f"Starting {agent_name} v{agent_version} (deploy: {deploy_id})")
    logger.info("Agent is running!")

    # Main loop - replace with your agent logic
    while True:
        logger.info(f"Heartbeat at {time.strftime('%%Y-%%m-%%d %%H:%%M:%%S')}")
        time.sleep(30)


if __name__ == "__main__":
    main()
`, name, name, name, name, name),

		"requirements.txt": `# Agent dependencies
# Add your dependencies here

# Common agent dependencies (uncomment as needed):
# requests>=2.28.0
# openai>=1.0.0
# anthropic>=0.5.0
# httpx>=0.24.0
`,

		"README.md": fmt.Sprintf(`# %s

AgentSpan agent project.

## Setup

`+"```bash"+`
pip install -r requirements.txt
`+"```"+`

## Run Locally

`+"```bash"+`
# Via AgentSpan runtime
agentspan agent run --config %s.yaml "Hello!"

# Or directly
python main.py
`+"```"+`

## Deploy

`+"```bash"+`
agentspan agent deploy --name %s
`+"```"+`

## Configuration

Edit `+"`%s.yaml`"+` to configure:
- Model (default: %s)
- Instructions
- Tools
- Max turns
`, name, name, name, name, model),
	}
}

func generateTypeScriptProject(name, model string) map[string]string {
	// Agent config YAML
	agentConfig := map[string]interface{}{
		"name":         name,
		"description":  fmt.Sprintf("%s agent", name),
		"model":        model,
		"instructions": fmt.Sprintf("You are %s, a helpful AI assistant.", name),
		"maxTurns":     25,
		"tools":        []interface{}{},
	}
	configYAML, _ := yaml.Marshal(agentConfig)

	return map[string]string{
		fmt.Sprintf("%s.yaml", name): string(configYAML),

		"src/index.ts": fmt.Sprintf(`/**
 * %s - AgentSpan Agent
 *
 * This agent can be run in two modes:
 * 1. Via AgentSpan runtime: agentspan agent run --config %s.yaml "prompt"
 * 2. Deployed to Kubernetes: agentspan agent deploy --name %s
 */

interface AgentConfig {
  name: string;
  version: string;
  deployId: string;
}

function getConfig(): AgentConfig {
  return {
    name: process.env.AGENT_NAME || '%s',
    version: process.env.AGENT_VERSION || 'dev',
    deployId: process.env.DEPLOY_ID || 'local',
  };
}

function log(message: string): void {
  const config = getConfig();
  console.log(`+"`[${config.name}] ${message}`"+`);
}

async function main(): Promise<void> {
  const config = getConfig();

  console.log(`+"`Starting ${config.name} v${config.version} (deploy: ${config.deployId})`"+`);
  console.log('Agent is running!');

  // Main loop - replace with your agent logic
  setInterval(() => {
    log(`+"`Heartbeat at ${new Date().toISOString()}`"+`);
  }, 30000);
}

main().catch(console.error);
`, name, name, name, name),

		"package.json": fmt.Sprintf(`{
  "name": "%s",
  "version": "1.0.0",
  "description": "AgentSpan agent",
  "main": "dist/index.js",
  "scripts": {
    "build": "tsc",
    "start": "node dist/index.js",
    "dev": "ts-node src/index.ts"
  },
  "dependencies": {},
  "devDependencies": {
    "typescript": "^5.3.0",
    "@types/node": "^20.0.0",
    "ts-node": "^10.9.0"
  }
}
`, name),

		"tsconfig.json": `{
  "compilerOptions": {
    "target": "ES2022",
    "module": "commonjs",
    "lib": ["ES2022"],
    "outDir": "./dist",
    "rootDir": "./src",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "declaration": true
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist"]
}
`,

		"README.md": fmt.Sprintf(`# %s

AgentSpan agent project.

## Setup

`+"```bash"+`
npm install
`+"```"+`

## Run Locally

`+"```bash"+`
# Via AgentSpan runtime
agentspan agent run --config %s.yaml "Hello!"

# Or directly
npm run dev
`+"```"+`

## Build

`+"```bash"+`
npm run build
`+"```"+`

## Deploy

`+"```bash"+`
agentspan agent deploy --name %s
`+"```"+`

## Configuration

Edit `+"`%s.yaml`"+` to configure:
- Model (default: %s)
- Instructions
- Tools
- Max turns
`, name, name, name, name, model),
	}
}

func generateJavaProject(name, model string) map[string]string {
	// Agent config YAML
	agentConfig := map[string]interface{}{
		"name":         name,
		"description":  fmt.Sprintf("%s agent", name),
		"model":        model,
		"instructions": fmt.Sprintf("You are %s, a helpful AI assistant.", name),
		"maxTurns":     25,
		"tools":        []interface{}{},
	}
	configYAML, _ := yaml.Marshal(agentConfig)

	return map[string]string{
		fmt.Sprintf("%s.yaml", name): string(configYAML),

		"src/main/java/Agent.java": fmt.Sprintf(`import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;

/**
 * %s - AgentSpan Agent
 *
 * This agent can be run in two modes:
 * 1. Via AgentSpan runtime: agentspan agent run --config %s.yaml "prompt"
 * 2. Deployed to Kubernetes: agentspan agent deploy --name %s
 */
public class Agent {
    private static final String AGENT_NAME = System.getenv().getOrDefault("AGENT_NAME", "%s");
    private static final String AGENT_VERSION = System.getenv().getOrDefault("AGENT_VERSION", "dev");
    private static final String DEPLOY_ID = System.getenv().getOrDefault("DEPLOY_ID", "local");

    public static void main(String[] args) throws InterruptedException {
        System.out.printf("Starting %%s v%%s (deploy: %%s)%%n", AGENT_NAME, AGENT_VERSION, DEPLOY_ID);
        System.out.println("Agent is running!");

        DateTimeFormatter formatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

        // Main loop - replace with your agent logic
        while (true) {
            String timestamp = LocalDateTime.now().format(formatter);
            System.out.printf("[%%s] Heartbeat at %%s%%n", AGENT_NAME, timestamp);
            Thread.sleep(30000);
        }
    }
}
`, name, name, name, name),

		"pom.xml": fmt.Sprintf(`<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.agentspan</groupId>
    <artifactId>%s</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <name>%s</name>
    <description>AgentSpan agent</description>

    <properties>
        <maven.compiler.source>21</maven.compiler.source>
        <maven.compiler.target>21</maven.compiler.target>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <!-- Add your dependencies here -->
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>Agent</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-shade-plugin</artifactId>
                <version>3.5.0</version>
                <executions>
                    <execution>
                        <phase>package</phase>
                        <goals>
                            <goal>shade</goal>
                        </goals>
                        <configuration>
                            <transformers>
                                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                                    <mainClass>Agent</mainClass>
                                </transformer>
                            </transformers>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
`, name, name),

		"README.md": fmt.Sprintf(`# %s

AgentSpan agent project.

## Setup

`+"```bash"+`
mvn package
`+"```"+`

## Run Locally

`+"```bash"+`
# Via AgentSpan runtime
agentspan agent run --config %s.yaml "Hello!"

# Or directly
java -jar target/%s-1.0.0.jar
`+"```"+`

## Deploy

`+"```bash"+`
agentspan agent deploy --name %s
`+"```"+`

## Configuration

Edit `+"`%s.yaml`"+` to configure:
- Model (default: %s)
- Instructions
- Tools
- Max turns
`, name, name, name, name, name, model),
	}
}
