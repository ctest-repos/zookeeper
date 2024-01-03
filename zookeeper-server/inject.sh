mvn test -Dtest=org.apache.zookeeper.server.quorum.FuzzySnapshotRelatedTest#testPZxidUpdatedWhenLoadingSnapshot -Dctest.config.save=true -Dconfig.inject.cli="connectToLearnerMasterLimit=xyz"
