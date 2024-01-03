/*
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

package org.apache.zookeeper.server;

import java.io.File;
import java.net.InetSocketAddress;
import java.util.Arrays;
import java.util.Properties;

import edu.illinois.ConfigTracker;
import org.apache.yetus.audience.InterfaceAudience;
import org.apache.zookeeper.metrics.impl.DefaultMetricsProvider;
import org.apache.zookeeper.server.quorum.QuorumPeerConfig;
import org.apache.zookeeper.server.quorum.QuorumPeerConfig.ConfigException;

/**
 * Server configuration storage.
 *
 * We use this instead of Properties as it's typed.
 *
 */
@InterfaceAudience.Public
public class ServerConfig {

    ////
    //// If you update the configuration parameters be sure
    //// to update the "conf" 4letter word
    ////
    protected InetSocketAddress clientPortAddress;
    protected InetSocketAddress secureClientPortAddress;
    protected File dataDir;
    protected File dataLogDir;
    protected int tickTime = ZooKeeperServer.DEFAULT_TICK_TIME;
    protected int maxClientCnxns;
    /** defaults to -1 if not set explicitly */
    protected int minSessionTimeout = -1;
    /** defaults to -1 if not set explicitly */
    protected int maxSessionTimeout = -1;
    protected String metricsProviderClassName = DefaultMetricsProvider.class.getName();
    protected Properties metricsProviderConfiguration = new Properties();
    /** defaults to -1 if not set explicitly */
    protected int listenBacklog = -1;
    protected String initialConfig;

    /** JVM Pause Monitor feature switch */
    protected boolean jvmPauseMonitorToRun = false;
    /** JVM Pause Monitor warn threshold in ms */
    protected long jvmPauseWarnThresholdMs;
    /** JVM Pause Monitor info threshold in ms */
    protected long jvmPauseInfoThresholdMs;
    /** JVM Pause Monitor sleep time in ms */
    protected long jvmPauseSleepTimeMs;

    /**
     * Parse arguments for server configuration
     * @param args clientPort dataDir and optional tickTime and maxClientCnxns
     * @throws IllegalArgumentException on invalid usage
     */
    public void parse(String[] args) {
        if (args.length < 2 || args.length > 4) {
            throw new IllegalArgumentException("Invalid number of arguments:" + Arrays.toString(args));
        }

        clientPortAddress = new InetSocketAddress(Integer.parseInt(args[0]));
        dataDir = new File(args[1]);
        dataLogDir = dataDir;
        if (args.length >= 3) {
            tickTime = Integer.parseInt(args[2]);
        }
        if (args.length == 4) {
            maxClientCnxns = Integer.parseInt(args[3]);
        }
    }

    /**
     * Parse a ZooKeeper configuration file
     * @param path the patch of the configuration file
     * @throws ConfigException error processing configuration
     */
    public void parse(String path) throws ConfigException {
        QuorumPeerConfig config = new QuorumPeerConfig();
        config.parse(path);

        // let qpconfig parse the file and then pull the stuff we are
        // interested in
        readFrom(config);
    }

    /**
     * Read attributes from a QuorumPeerConfig.
     * @param config
     */
    public void readFrom(QuorumPeerConfig config) {
        clientPortAddress = config.getClientPortAddress();
        secureClientPortAddress = config.getSecureClientPortAddress();
        dataDir = config.getDataDir();
        dataLogDir = config.getDataLogDir();
        tickTime = config.getTickTime();
        maxClientCnxns = config.getMaxClientCnxns();
        minSessionTimeout = config.getMinSessionTimeout();
        maxSessionTimeout = config.getMaxSessionTimeout();
        jvmPauseMonitorToRun = config.isJvmPauseMonitorToRun();
        jvmPauseInfoThresholdMs = config.getJvmPauseInfoThresholdMs();
        jvmPauseWarnThresholdMs = config.getJvmPauseWarnThresholdMs();
        jvmPauseSleepTimeMs = config.getJvmPauseSleepTimeMs();
        metricsProviderClassName = config.getMetricsProviderClassName();
        metricsProviderConfiguration = config.getMetricsProviderConfiguration();
        listenBacklog = config.getClientPortListenBacklog();
        initialConfig = config.getInitialConfig();
    }

    public InetSocketAddress getClientPortAddress() {
        ConfigTracker.markParamAsUsed("clientPortAddress");
        return clientPortAddress;
    }
    public InetSocketAddress getSecureClientPortAddress() {
        ConfigTracker.markParamAsUsed("secureClientPortAddress");
        return secureClientPortAddress;
    }
    public File getDataDir() {
        ConfigTracker.markParamAsUsed("dataDir");
        return dataDir;
    }
    public File getDataLogDir() {
        ConfigTracker.markParamAsUsed("dataLogDir");
        return dataLogDir;
    }
    public int getTickTime() {
        ConfigTracker.markParamAsUsed("tickTime");
        return tickTime;
    }
    public int getMaxClientCnxns() {
        ConfigTracker.markParamAsUsed("maxClientCnxns");
        return maxClientCnxns;
    }
    /** minimum session timeout in milliseconds, -1 if unset */
    public int getMinSessionTimeout() {
        ConfigTracker.markParamAsUsed("minSessionTimeout");
        return minSessionTimeout;
    }
    /** maximum session timeout in milliseconds, -1 if unset */
    public int getMaxSessionTimeout() {
        ConfigTracker.markParamAsUsed("maxSessionTimeout");
        return maxSessionTimeout;
    }

    public long getJvmPauseInfoThresholdMs() {
        ConfigTracker.markParamAsUsed("jvmPauseInfoThresholdMs");
        return jvmPauseInfoThresholdMs;
    }
    public long getJvmPauseWarnThresholdMs() {
        ConfigTracker.markParamAsUsed("jvmPauseWarnThresholdMs");
        return jvmPauseWarnThresholdMs;
    }
    public long getJvmPauseSleepTimeMs() {
        ConfigTracker.markParamAsUsed("jvmPauseSleepTimeMs");
        return jvmPauseSleepTimeMs;
    }
    public boolean isJvmPauseMonitorToRun() {
        ConfigTracker.markParamAsUsed("jvmPauseMonitorToRun");
        return jvmPauseMonitorToRun;
    }
    public String getMetricsProviderClassName() {
        ConfigTracker.markParamAsUsed("metricsProviderClassName");
        return metricsProviderClassName;
    }
    public Properties getMetricsProviderConfiguration() {
        ConfigTracker.markParamAsUsed("metricsProviderConfiguration");
        return metricsProviderConfiguration;
    }
    /** Maximum number of pending socket connections to read, -1 if unset */
    public int getClientPortListenBacklog() {
        ConfigTracker.markParamAsUsed("listenBacklog");
        return listenBacklog;
    }

}
