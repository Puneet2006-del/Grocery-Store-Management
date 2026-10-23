package com.zerowaste.grocery.service;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * Starts pipeline/onboard_shops.py in the background when a shop is added. That job creates the new shop's
 * start-up history, then retrains the forecasts and runs the agents. It uses the project's own Python
 * environment (venv) when there is one. One job runs at a time; it keeps going until no shop is waiting.
 */
@Component
public class OnboardingLauncher {

    private final boolean enabled;
    private final String projectRoot;
    private Process running;

    public OnboardingLauncher(@Value("${app.onboarding.enabled:true}") boolean enabled,
                              @Value("${app.project-root:}") String projectRoot) {
        this.enabled = enabled;
        this.projectRoot = projectRoot;
    }

    /** Returns "started" or "already running" on success, otherwise a reason. */
    public synchronized String start() {
        if (!enabled) {
            return "automatic set-up is switched off (app.onboarding.enabled=false)";
        }
        if (running != null && running.isAlive()) {
            return "already running";
        }
        Path root = projectRoot.isBlank() ? Path.of("").toAbsolutePath().getParent() : Path.of(projectRoot);
        Path script = root.resolve("pipeline").resolve("onboard_shops.py");
        if (!Files.exists(script)) {
            return "set-up script not found at " + script;
        }
        Path venvWindows = root.resolve("venv").resolve("Scripts").resolve("python.exe");
        Path venvUnix = root.resolve("venv").resolve("bin").resolve("python");
        String python = Files.exists(venvWindows) ? venvWindows.toString()
                : Files.exists(venvUnix) ? venvUnix.toString() : "python";
        try {
            Path logDir = root.resolve("data-pipeline").resolve("data").resolve("reports");
            Files.createDirectories(logDir);
            ProcessBuilder pb = new ProcessBuilder(python, script.toString())
                    .directory(root.toFile())
                    .redirectErrorStream(true)
                    .redirectOutput(ProcessBuilder.Redirect.appendTo(logDir.resolve("onboarding.log").toFile()));
            running = pb.start();
            return "started";
        } catch (IOException e) {
            return "could not start the set-up job: " + e.getMessage();
        }
    }
}
