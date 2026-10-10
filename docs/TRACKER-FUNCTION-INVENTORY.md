# Tracker named-function destination inventory

Source: `95cba831a77fd47f9499963ae9dfef9761d4e57b`, `index.html`. All 620 named declarations are listed, including repeated names. Repeated names may be locally scoped; name repetition alone does not prove an override. This maps helpers to the native subsystem that replaces their responsibility. It is not a claim of copying each function or testing every source branch independently. Acceptance behaviour and intentional replacements are specified in [TRACKER-PARITY.md](TRACKER-PARITY.md); actual test evidence is in [HUB-COMPLETION.md](HUB-COMPLETION.md).

| Source function | Line | Native destination / replacement subsystem |
|---|---:|---|
| `setTutorialFresh` | 6197 | Native installation and contextual help |
| `tutorialFreshActive` | 6198 | Native installation and contextual help |
| `clearTutorialFresh` | 6202 | Native installation and contextual help |
| `tutorialResetTargetFromUrl` | 6203 | Native installation and contextual help |
| `rememberTutorialResetRequest` | 6211 | Typed declarations, wizards, project/media details and review |
| `pendingTutorialResetTarget` | 6216 | Native installation and contextual help |
| `clearTutorialResetRequest` | 6220 | Typed declarations, wizards, project/media details and review |
| `maybeResetTutorialAccount` | 6228 | Native installation and contextual help |
| `isEmailAllowed` | 6284 | Identity, profiles and server roles |
| `enforceEmailAllowlist` | 6291 | Delivery, in-app notifications and admin outbox |
| `refreshAuthSession` | 6323 | Identity, profiles and server roles |
| `syncProfileFromAuth` | 6340 | Identity, profiles and server roles |
| `signInWithGoogle` | 6356 | Identity, profiles and server roles |
| `signOut` | 6364 | Identity, profiles and server roles |
| `persistDeptRoleToAuthMetadata` | 6374 | Identity, profiles and server roles |
| `isLocalDev` | 6399 | Accessible SUI layout, navigation, settings and rendering |
| `devBypassSignIn` | 6403 | Identity, profiles and server roles |
| `mountDevBypass` | 6422 | Accessible SUI layout, navigation, settings and rendering |
| `migrate` | 6448 | Business calculations, financial assumptions and plan pricing |
| `loadJSON` | 6471 | Canonical SQLite APIs and read-only import/export |
| `saveJSON` | 6475 | Canonical SQLite APIs and read-only import/export |
| `saveEntries` | 6481 | Canonical SQLite APIs and read-only import/export |
| `markUnsynced` | 6492 | Canonical SQLite APIs and read-only import/export |
| `markSynced` | 6499 | Canonical SQLite APIs and read-only import/export |
| `hasUnsyncedWork` | 6504 | Canonical SQLite APIs and read-only import/export |
| `reportSave` | 6508 | Typed declarations, wizards, project/media details and review |
| `saveSettings` | 6522 | Accessible SUI layout, navigation, settings and rendering |
| `saveProfile` | 6523 | Identity, profiles and server roles |
| `uid` | 6524 | Accessible SUI layout, navigation, settings and rendering |
| `backendSyncDebounced` | 6566 | Canonical SQLite APIs and read-only import/export |
| `retryPendingSync` | 6587 | Canonical SQLite APIs and read-only import/export |
| `mergeEntries` | 6598 | Canonical SQLite APIs and read-only import/export |
| `autoSyncOnLoad` | 6617 | Canonical SQLite APIs and read-only import/export |
| `backendPushAll` | 6672 | Canonical SQLite APIs and read-only import/export |
| `backendPullAll` | 6687 | Canonical SQLite APIs and read-only import/export |
| `sheetsPushAll` | 6716 | Canonical SQLite APIs and read-only import/export |
| `sheetsPullAll` | 6739 | Canonical SQLite APIs and read-only import/export |
| `supabaseHeaders` | 6760 | Canonical SQLite APIs and read-only import/export |
| `supabaseEndpoint` | 6776 | Canonical SQLite APIs and read-only import/export |
| `configCreds` | 6822 | Canonical SQLite APIs and read-only import/export |
| `configHeaders` | 6830 | Canonical SQLite APIs and read-only import/export |
| `configPull` | 6845 | Canonical SQLite APIs and read-only import/export |
| `applyDriveConfig` | 6863 | Accessible SUI layout, navigation, settings and rendering |
| `applyAdminsConfig` | 6876 | Identity, profiles and server roles |
| `applyNotifyConfig` | 6907 | Delivery, in-app notifications and admin outbox |
| `configPut` | 6929 | Canonical SQLite APIs and read-only import/export |
| `configPushDrive` | 6950 | Canonical SQLite APIs and read-only import/export |
| `configPushAdminPass` | 6955 | Identity, profiles and server roles |
| `applyAdminPassConfig` | 6974 | Identity, profiles and server roles |
| `configPushAdmins` | 7000 | Canonical SQLite APIs and read-only import/export |
| `configPushDriveDebounced` | 7005 | Canonical SQLite APIs and read-only import/export |
| `refreshDriveUi` | 7017 | Accessible SUI layout, navigation, settings and rendering |
| `supabasePushAll` | 7024 | Canonical SQLite APIs and read-only import/export |
| `supabaseDeleteIds` | 7057 | Canonical SQLite APIs and read-only import/export |
| `supabaseDeleteAllRemote` | 7068 | Canonical SQLite APIs and read-only import/export |
| `backendDeleteEntry` | 7080 | Canonical SQLite APIs and read-only import/export |
| `backendDeleteEntries` | 7081 | Canonical SQLite APIs and read-only import/export |
| `supabasePullAll` | 7089 | Canonical SQLite APIs and read-only import/export |
| `realtimePullAndRender` | 7118 | Accessible SUI layout, navigation, settings and rendering |
| `scheduleRealtimePull` | 7142 | Accessible SUI layout, navigation, settings and rendering |
| `startRealtime` | 7147 | Accessible SUI layout, navigation, settings and rendering |
| `stopRealtime` | 7171 | Accessible SUI layout, navigation, settings and rendering |
| `fmtUSD` | 7179 | Business calculations, financial assumptions and plan pricing |
| `fmtUSDp` | 7196 | Business calculations, financial assumptions and plan pricing |
| `fmtUGX` | 7206 | Business calculations, financial assumptions and plan pricing |
| `fmtHours` | 7213 | Business calculations, financial assumptions and plan pricing |
| `_normalizeKey` | 7431 | Canonical catalogue and historical registry |
| `_stripUrlTrail` | 7439 | Canonical catalogue and historical registry |
| `getDynamicRegistry` | 7444 | Canonical catalogue and historical registry |
| `fullRegistry` | 7466 | Canonical catalogue and historical registry |
| `findToolInRegistry` | 7469 | Canonical catalogue and historical registry |
| `canonicalToolName` | 7480 | Canonical catalogue and historical registry |
| `canonicalToolUrl` | 7484 | Canonical catalogue and historical registry |
| `toolLinkHTML` | 7492 | Accessible SUI layout, navigation, settings and rendering |
| `toHours` | 7515 | Business calculations, financial assumptions and plan pricing |
| `smartUnit` | 7523 | Business calculations, financial assumptions and plan pricing |
| `fmtDuration` | 7536 | Business calculations, financial assumptions and plan pricing |
| `fmtEntryTime` | 7545 | Accessible SUI layout, navigation, settings and rendering |
| `switchView` | 7557 | Accessible SUI layout, navigation, settings and rendering |
| `hashPassword` | 7581 | Identity, profiles and server roles |
| `sha256` | 7600 | Accessible SUI layout, navigation, settings and rendering |
| `showAdminContent` | 7602 | Accessible SUI layout, navigation, settings and rendering |
| `showAdminGateOnly` | 7606 | Identity, profiles and server roles |
| `gateError` | 7611 | Identity, profiles and server roles |
| `renderAdminGate` | 7618 | Identity, profiles and server roles |
| `setAdminPassword` | 7667 | Identity, profiles and server roles |
| `unlockAdmin` | 7690 | Accessible SUI layout, navigation, settings and rendering |
| `lockAdmin` | 7715 | Accessible SUI layout, navigation, settings and rendering |
| `changeAdminPassword` | 7725 | Identity, profiles and server roles |
| `requestPasswordReset` | 7736 | Identity, profiles and server roles |
| `goToUser` | 7746 | Accessible SUI layout, navigation, settings and rendering |
| `renderProfileInputs` | 7754 | Identity, profiles and server roles |
| `saveProfileAndContinue` | 7760 | Identity, profiles and server roles |
| `isMyEntry` | 7783 | Accessible SUI layout, navigation, settings and rendering |
| `myEntries` | 7794 | Accessible SUI layout, navigation, settings and rendering |
| `_normalizeStr` | 7797 | Canonical catalogue and historical registry |
| `findClaimCandidates` | 7803 | Typed declarations, wizards, project/media details and review |
| `adoptEntries` | 7823 | Scoped analytics, management documents and exports |
| `renderClaimBanner` | 7841 | Typed declarations, wizards, project/media details and review |
| `adoptSelectedFromBanner` | 7874 | Accessible SUI layout, navigation, settings and rendering |
| `dismissClaimBanner` | 7879 | Typed declarations, wizards, project/media details and review |
| `renderProfileBadge` | 7885 | Identity, profiles and server roles |
| `statusPillClass` | 7909 | Accessible SUI layout, navigation, settings and rendering |
| `dismissDeptPromptNow` | 7916 | Accessible SUI layout, navigation, settings and rendering |
| `addNewTool` | 7925 | Typed declarations, wizards, project/media details and review |
| `openTool` | 7939 | Accessible SUI layout, navigation, settings and rendering |
| `removeTool` | 7950 | Isolated synthetic fixtures and governed archival |
| `preserveRegistryStubIfNeeded` | 7964 | Canonical catalogue and historical registry |
| `backToTools` | 7983 | Accessible SUI layout, navigation, settings and rendering |
| `updateProject` | 7990 | Typed declarations, wizards, project/media details and review |
| `populateToolRegistryDatalist` | 7997 | Canonical catalogue and historical registry |
| `toolPickerEl` | 8043 | Canonical catalogue and historical registry |
| `toolPickerPlace` | 8055 | Canonical catalogue and historical registry |
| `toolPickerRows` | 8072 | Canonical catalogue and historical registry |
| `toolPickerMatches` | 8082 | Canonical catalogue and historical registry |
| `toolPickerRender` | 8093 | Canonical catalogue and historical registry |
| `toolPickerOpen` | 8127 | Canonical catalogue and historical registry |
| `toolPickerClose` | 8135 | Canonical catalogue and historical registry |
| `toolPickerToggle` | 8142 | Canonical catalogue and historical registry |
| `toolPickerChoose` | 8147 | Canonical catalogue and historical registry |
| `toolPickerKey` | 8158 | Canonical catalogue and historical registry |
| `onToolNameInput` | 8197 | Accessible SUI layout, navigation, settings and rendering |
| `populatePlanSuggestions` | 8237 | Business calculations, financial assumptions and plan pricing |
| `onPlanSelected` | 8273 | Business calculations, financial assumptions and plan pricing |
| `selectedPublishedPlan` | 8294 | Business calculations, financial assumptions and plan pricing |
| `usagePricingSourceForEntry` | 8304 | Business calculations, financial assumptions and plan pricing |
| `clearDetailForm` | 8315 | Typed declarations, wizards, project/media details and review |
| `loadDetailForm` | 8338 | Typed declarations, wizards, project/media details and review |
| `saveDetail` | 8365 | Typed declarations, wizards, project/media details and review |
| `deleteCurrent` | 8505 | Isolated synthetic fixtures and governed archival |
| `onDetailDirty` | 8521 | Typed declarations, wizards, project/media details and review |
| `openWizard` | 8537 | Typed declarations, wizards, project/media details and review |
| `closeWizard` | 8558 | Typed declarations, wizards, project/media details and review |
| `dismissOverlays` | 8569 | Accessible SUI layout, navigation, settings and rendering |
| `applyWizardMode` | 8584 | Typed declarations, wizards, project/media details and review |
| `setWizardTag` | 8606 | Typed declarations, wizards, project/media details and review |
| `validateStep` | 8616 | Typed declarations, wizards, project/media details and review |
| `showStepError` | 8632 | Typed declarations, wizards, project/media details and review |
| `clearStepError` | 8636 | Typed declarations, wizards, project/media details and review |
| `clearAllStepErrors` | 8640 | Typed declarations, wizards, project/media details and review |
| `finishWizard` | 8641 | Typed declarations, wizards, project/media details and review |
| `openAddChooser` | 8651 | Typed declarations, wizards, project/media details and review |
| `closeAddChooser` | 8661 | Typed declarations, wizards, project/media details and review |
| `chooseAddType` | 8667 | Typed declarations, wizards, project/media details and review |
| `startPublicRequest` | 8670 | Accessible SUI layout, navigation, settings and rendering |
| `submitPublicRequest` | 8679 | Accessible SUI layout, navigation, settings and rendering |
| `insertPublicRequestRow` | 8749 | Accessible SUI layout, navigation, settings and rendering |
| `requestEntries` | 8775 | Accessible SUI layout, navigation, settings and rendering |
| `setRequestStatus` | 8776 | Typed declarations, wizards, project/media details and review |
| `setRequestNote` | 8784 | Typed declarations, wizards, project/media details and review |
| `saveDetailDraftDebounced` | 8800 | Typed declarations, wizards, project/media details and review |
| `saveDetailDraftNow` | 8804 | Typed declarations, wizards, project/media details and review |
| `loadDetailDraft` | 8836 | Typed declarations, wizards, project/media details and review |
| `clearDetailDraft` | 8844 | Typed declarations, wizards, project/media details and review |
| `applyDraftToForm` | 8847 | Accessible SUI layout, navigation, settings and rendering |
| `usageUnitLabel` | 8882 | Business calculations, financial assumptions and plan pricing |
| `toolIsFlatRate` | 8899 | Business calculations, financial assumptions and plan pricing |
| `defaultUsageUnitForTool` | 8904 | Business calculations, financial assumptions and plan pricing |
| `toolPricingBaseline` | 8922 | Business calculations, financial assumptions and plan pricing |
| `usagePricingSource` | 8931 | Business calculations, financial assumptions and plan pricing |
| `usageCostMethodLabel` | 8939 | Business calculations, financial assumptions and plan pricing |
| `syncUsagePricingUI` | 8952 | Business calculations, financial assumptions and plan pricing |
| `computeUsageCost` | 9020 | Business calculations, financial assumptions and plan pricing |
| `updateConversions` | 9109 | Accessible SUI layout, navigation, settings and rendering |
| `renderCostSummary` | 9148 | Business calculations, financial assumptions and plan pricing |
| `updateRate` | 9227 | Business calculations, financial assumptions and plan pricing |
| `licenceSharers` | 9255 | Business calculations, financial assumptions and plan pricing |
| `monthlySavings` | 9273 | Business calculations, financial assumptions and plan pricing |
| `populateAdminFilters` | 9312 | Scoped analytics, management documents and exports |
| `isRegistryStub` | 9327 | Canonical catalogue and historical registry |
| `dashboardEntries` | 9328 | Scoped analytics, management documents and exports |
| `registryStubs` | 9329 | Canonical catalogue and historical registry |
| `filteredEntries` | 9331 | Scoped analytics, management documents and exports |
| `renderAdmin` | 9346 | Accessible SUI layout, navigation, settings and rendering |
| `renderExecReport` | 9451 | Scoped analytics, management documents and exports |
| `_toolGroupKey` | 9502 | Canonical catalogue and historical registry |
| `_toolGroups` | 9507 | Canonical catalogue and historical registry |
| `startReassign` | 9524 | Typed declarations, wizards, project/media details and review |
| `cancelReassign` | 9556 | Typed declarations, wizards, project/media details and review |
| `saveReassign` | 9560 | Typed declarations, wizards, project/media details and review |
| `renderToolsEntered` | 9577 | Scoped analytics, management documents and exports |
| `returnPerDollar` | 9637 | Business calculations, financial assumptions and plan pricing |
| `buildToolReport` | 9641 | Scoped analytics, management documents and exports |
| `toolDrillHTML` | 9724 | Scoped analytics, management documents and exports |
| `showToolDrillDown` | 9801 | Scoped analytics, management documents and exports |
| `copyToolReport` | 9807 | Scoped analytics, management documents and exports |
| `hideToolDrillDown` | 9872 | Scoped analytics, management documents and exports |
| `renderRegistryManager` | 9881 | Canonical catalogue and historical registry |
| `addRegistryToolFromAdmin` | 9950 | Canonical catalogue and historical registry |
| `deleteRegistryTool` | 9988 | Canonical catalogue and historical registry |
| `renderRotationTable` | 10004 | Business calculations, financial assumptions and plan pricing |
| `renderCategoryBars` | 10037 | Scoped analytics, management documents and exports |
| `renderStatusChart` | 10062 | Accessible SUI layout, navigation, settings and rendering |
| `renderRevenueBars` | 10087 | Business calculations, financial assumptions and plan pricing |
| `exportJSON` | 10113 | Scoped analytics, management documents and exports |
| `exportCSV` | 10116 | Scoped analytics, management documents and exports |
| `download` | 10145 | Scoped analytics, management documents and exports |
| `val` | 10155 | Accessible SUI layout, navigation, settings and rendering |
| `num` | 10156 | Business calculations, financial assumptions and plan pricing |
| `set` | 10157 | Accessible SUI layout, navigation, settings and rendering |
| `escapeHTML` | 10158 | Accessible SUI layout, navigation, settings and rendering |
| `escapeAttr` | 10159 | Accessible SUI layout, navigation, settings and rendering |
| `passwordInputHTML` | 10160 | Identity, profiles and server roles |
| `togglePasswordVisibility` | 10167 | Identity, profiles and server roles |
| `safeUrl` | 10182 | Accessible SUI layout, navigation, settings and rendering |
| `jsArg` | 10205 | Accessible SUI layout, navigation, settings and rendering |
| `urlCellHTML` | 10210 | Accessible SUI layout, navigation, settings and rendering |
| `toast` | 10219 | Accessible SUI layout, navigation, settings and rendering |
| `wipeAll` | 10230 | Isolated synthetic fixtures and governed archival |
| `renderBackendSettings` | 10240 | Canonical SQLite APIs and read-only import/export |
| `onBackendModeChange` | 10253 | Canonical SQLite APIs and read-only import/export |
| `saveBackendConfig` | 10258 | Canonical SQLite APIs and read-only import/export |
| `testBackendConnection` | 10270 | Canonical SQLite APIs and read-only import/export |
| `manualPushAll` | 10294 | Canonical SQLite APIs and read-only import/export |
| `manualPullAll` | 10298 | Canonical SQLite APIs and read-only import/export |
| `renderBackendStatus` | 10302 | Canonical SQLite APIs and read-only import/export |
| `importJSONFile` | 10331 | Accessible SUI layout, navigation, settings and rendering |
| `routeSignedIn` | 10382 | Accessible SUI layout, navigation, settings and rendering |
| `manualSyncNow` | 10458 | Canonical SQLite APIs and read-only import/export |
| `seedDemo` | 10475 | Isolated synthetic fixtures and governed archival |
| `boot` | 10618 | Accessible SUI layout, navigation, settings and rendering |
| `salutation` | 10800 | Accessible SUI layout, navigation, settings and rendering |
| `sync` | 10806 | Canonical SQLite APIs and read-only import/export |
| `normEmail` | 10839 | Delivery, in-app notifications and admin outbox |
| `isSuperAdmin` | 10840 | Accessible SUI layout, navigation, settings and rendering |
| `extraAdmins` | 10841 | Identity, profiles and server roles |
| `saveExtraAdmins` | 10845 | Identity, profiles and server roles |
| `currentEmail` | 10851 | Identity, profiles and server roles |
| `currentRole` | 10854 | Identity, profiles and server roles |
| `canSeeAdmin` | 10861 | Accessible SUI layout, navigation, settings and rendering |
| `otpState` | 10895 | Identity, profiles and server roles |
| `setOtpState` | 10898 | Identity, profiles and server roles |
| `randomCode` | 10902 | Accessible SUI layout, navigation, settings and rendering |
| `sendAdminOtp` | 10907 | Identity, profiles and server roles |
| `verifyAdminOtp` | 10934 | Identity, profiles and server roles |
| `otpVerified` | 10947 | Identity, profiles and server roles |
| `otpAvailable` | 10959 | Identity, profiles and server roles |
| `adminPassStore` | 11070 | Identity, profiles and server roles |
| `saveAdminPassStore` | 11073 | Identity, profiles and server roles |
| `adminPassRecord` | 11076 | Identity, profiles and server roles |
| `_hex` | 11077 | Accessible SUI layout, navigation, settings and rendering |
| `derivePass` | 11082 | Accessible SUI layout, navigation, settings and rendering |
| `randomSaltHex` | 11095 | Accessible SUI layout, navigation, settings and rendering |
| `setAdminPassFor` | 11101 | Identity, profiles and server roles |
| `verifyAdminPass` | 11116 | Identity, profiles and server roles |
| `clearAdminPassFor` | 11122 | Identity, profiles and server roles |
| `adoptLegacyAdminPassword` | 11150 | Identity, profiles and server roles |
| `adminGateCard` | 11159 | Identity, profiles and server roles |
| `pullMyAdminPassRecord` | 11175 | Identity, profiles and server roles |
| `renderAdminPasswordGate` | 11203 | Identity, profiles and server roles |
| `accountMenuEl` | 11378 | Accessible SUI layout, navigation, settings and rendering |
| `accountMenuOpen` | 11389 | Accessible SUI layout, navigation, settings and rendering |
| `renderAccountMenu` | 11390 | Accessible SUI layout, navigation, settings and rendering |
| `openAccountMenu` | 11423 | Accessible SUI layout, navigation, settings and rendering |
| `closeAccountMenu` | 11440 | Accessible SUI layout, navigation, settings and rendering |
| `toggleAccountMenu` | 11445 | Accessible SUI layout, navigation, settings and rendering |
| `openAdminDashboard` | 11463 | Scoped analytics, management documents and exports |
| `paintAdminDoor` | 11487 | Accessible SUI layout, navigation, settings and rendering |
| `monthKey` | 11537 | Scoped analytics, management documents and exports |
| `monthLabel` | 11538 | Scoped analytics, management documents and exports |
| `lastMonths` | 11542 | Scoped analytics, management documents and exports |
| `smoothPath` | 11548 | Accessible SUI layout, navigation, settings and rendering |
| `renderTrendChart` | 11560 | Scoped analytics, management documents and exports |
| `renderDeptDonut` | 11619 | Scoped analytics, management documents and exports |
| `renderTopTools` | 11651 | Scoped analytics, management documents and exports |
| `renderKpiSparks` | 11677 | Accessible SUI layout, navigation, settings and rendering |
| `renderAdminsPanel` | 11727 | Accessible SUI layout, navigation, settings and rendering |
| `addAdminEmail` | 11753 | Identity, profiles and server roles |
| `removeAdminEmail` | 11772 | Identity, profiles and server roles |
| `publishAdmins` | 11782 | Identity, profiles and server roles |
| `adminsPublishLine` | 11797 | Accessible SUI layout, navigation, settings and rendering |
| `applyRoleChrome` | 11841 | Accessible SUI layout, navigation, settings and rendering |
| `paintRailAccount` | 11853 | Accessible SUI layout, navigation, settings and rendering |
| `graphModel` | 11904 | Scoped analytics, management documents and exports |
| `renderUsageGraph` | 11923 | Scoped analytics, management documents and exports |
| `selectGraphNode` | 12010 | Scoped analytics, management documents and exports |
| `graphZoom` | 12079 | Scoped analytics, management documents and exports |
| `graphReset` | 12084 | Scoped analytics, management documents and exports |
| `buildFindings` | 12087 | Scoped analytics, management documents and exports |
| `aiReportText` | 12141 | Scoped analytics, management documents and exports |
| `copyAiReport` | 12148 | Scoped analytics, management documents and exports |
| `printAiReport` | 12153 | Scoped analytics, management documents and exports |
| `seedDemoData` | 12191 | Isolated synthetic fixtures and governed archival |
| `clearDemoData` | 12230 | Isolated synthetic fixtures and governed archival |
| `size` | 12276 | Accessible SUI layout, navigation, settings and rendering |
| `frame` | 12288 | Accessible SUI layout, navigation, settings and rendering |
| `start` | 12302 | Accessible SUI layout, navigation, settings and rendering |
| `stop` | 12303 | Accessible SUI layout, navigation, settings and rendering |
| `buildAdminNav` | 12316 | Accessible SUI layout, navigation, settings and rendering |
| `showAdminSection` | 12328 | Accessible SUI layout, navigation, settings and rendering |
| `appScrollTop` | 12365 | Accessible SUI layout, navigation, settings and rendering |
| `apply` | 12384 | Accessible SUI layout, navigation, settings and rendering |
| `deptSub` | 12417 | Accessible SUI layout, navigation, settings and rendering |
| `renderDeptPicker` | 12418 | Identity, profiles and server roles |
| `pickDepartment` | 12439 | Identity, profiles and server roles |
| `updateOnboardHint` | 12445 | Identity, profiles and server roles |
| `openPanels` | 12524 | Accessible SUI layout, navigation, settings and rendering |
| `setPanelOpen` | 12527 | Accessible SUI layout, navigation, settings and rendering |
| `buildDisclosures` | 12535 | Accessible SUI layout, navigation, settings and rendering |
| `paletteCommands` | 12584 | Accessible SUI layout, navigation, settings and rendering |
| `openPalette` | 12627 | Accessible SUI layout, navigation, settings and rendering |
| `closePalette` | 12635 | Accessible SUI layout, navigation, settings and rendering |
| `renderPalette` | 12636 | Accessible SUI layout, navigation, settings and rendering |
| `movePalette` | 12650 | Accessible SUI layout, navigation, settings and rendering |
| `runPalette` | 12657 | Accessible SUI layout, navigation, settings and rendering |
| `startPurpose` | 12725 | Typed declarations, wizards, project/media details and review |
| `choosePurpose` | 12741 | Typed declarations, wizards, project/media details and review |
| `openGuidedWizard` | 12750 | Typed declarations, wizards, project/media details and review |
| `showDone` | 12799 | Accessible SUI layout, navigation, settings and rendering |
| `deptAccessState` | 12880 | Department report scopes |
| `saveDeptAccess` | 12884 | Department report scopes |
| `openProfileSettings` | 12886 | Identity, profiles and server roles |
| `closeProfileSettings` | 12914 | Identity, profiles and server roles |
| `renderProfileAvatar` | 12920 | Identity, profiles and server roles |
| `onProfilePhoto` | 12927 | Identity, profiles and server roles |
| `clearProfilePhoto` | 12953 | Identity, profiles and server roles |
| `renderDeptAccess` | 12958 | Department report scopes |
| `submitAccessRequest` | 12984 | Department report scopes |
| `changePasswordFromProfile` | 13019 | Identity, profiles and server roles |
| `saveProfileSettings` | 13045 | Identity, profiles and server roles |
| `installEvent` | 13098 | Native installation and contextual help |
| `isStandalone` | 13100 | Native installation and contextual help |
| `isIOS` | 13104 | Native installation and contextual help |
| `paintInstall` | 13115 | Native installation and contextual help |
| `installApp` | 13134 | Native installation and contextual help |
| `setTheme` | 13168 | Accessible SUI layout, navigation, settings and rendering |
| `toggleProfileMenu` | 13188 | Identity, profiles and server roles |
| `closeProfileMenu` | 13198 | Identity, profiles and server roles |
| `deptEntries` | 13214 | Scoped analytics, management documents and exports |
| `tourDoneFor` | 13236 | Native installation and contextual help |
| `markTourDone` | 13240 | Native installation and contextual help |
| `tourSteps` | 13246 | Typed declarations, wizards, project/media details and review |
| `startTour` | 13280 | Native installation and contextual help |
| `paintTourStep` | 13290 | Typed declarations, wizards, project/media details and review |
| `nextTourStep` | 13369 | Typed declarations, wizards, project/media details and review |
| `prevTourStep` | 13370 | Typed declarations, wizards, project/media details and review |
| `endTour` | 13371 | Native installation and contextual help |
| `botDept` | 13397 | Native installation and contextual help |
| `botMyEntries` | 13398 | Native installation and contextual help |
| `botStats` | 13404 | Scoped analytics, management documents and exports |
| `botAnswer` | 13410 | Native installation and contextual help |
| `botPush` | 13529 | Identity, profiles and server roles |
| `botSend` | 13538 | Native installation and contextual help |
| `botToggle` | 13546 | Native installation and contextual help |
| `apply` | 13570 | Accessible SUI layout, navigation, settings and rendering |
| `sectionSub` | 13633 | Accessible SUI layout, navigation, settings and rendering |
| `groupOf` | 13638 | Accessible SUI layout, navigation, settings and rendering |
| `groupBadge` | 13644 | Accessible SUI layout, navigation, settings and rendering |
| `inboxPending` | 13658 | Accessible SUI layout, navigation, settings and rendering |
| `settingsPending` | 13669 | Accessible SUI layout, navigation, settings and rendering |
| `buildRailGroups` | 13684 | Accessible SUI layout, navigation, settings and rendering |
| `railMenuEl` | 13751 | Accessible SUI layout, navigation, settings and rendering |
| `renderRailMenu` | 13763 | Accessible SUI layout, navigation, settings and rendering |
| `railMenuOpen` | 13785 | Accessible SUI layout, navigation, settings and rendering |
| `groupButton` | 13788 | Accessible SUI layout, navigation, settings and rendering |
| `openRailMenu` | 13792 | Accessible SUI layout, navigation, settings and rendering |
| `closeRailMenu` | 13819 | Accessible SUI layout, navigation, settings and rendering |
| `toggleRailMenu` | 13827 | Accessible SUI layout, navigation, settings and rendering |
| `chooseSection` | 13831 | Typed declarations, wizards, project/media details and review |
| `syncGroupActive` | 13838 | Canonical SQLite APIs and read-only import/export |
| `humanBackendMsg` | 13898 | Canonical SQLite APIs and read-only import/export |
| `syncBackendWarning` | 13948 | Canonical SQLite APIs and read-only import/export |
| `previewHost` | 14018 | Accessible SUI layout, navigation, settings and rendering |
| `previewAsDept` | 14019 | Accessible SUI layout, navigation, settings and rendering |
| `togglePreviewAsDept` | 14030 | Accessible SUI layout, navigation, settings and rendering |
| `updatePreviewDeptBtn` | 14040 | Accessible SUI layout, navigation, settings and rendering |
| `positions` | 14109 | Accessible SUI layout, navigation, settings and rendering |
| `savePosition` | 14112 | Accessible SUI layout, navigation, settings and rendering |
| `forgetPosition` | 14125 | Accessible SUI layout, navigation, settings and rendering |
| `scope` | 14139 | Accessible SUI layout, navigation, settings and rendering |
| `mount` | 14147 | Accessible SUI layout, navigation, settings and rendering |
| `persist` | 14163 | Canonical SQLite APIs and read-only import/export |
| `readPersisted` | 14170 | Canonical SQLite APIs and read-only import/export |
| `keyOf` | 14174 | Accessible SUI layout, navigation, settings and rendering |
| `open` | 14182 | Accessible SUI layout, navigation, settings and rendering |
| `show` | 14226 | Accessible SUI layout, navigation, settings and rendering |
| `place` | 14300 | Accessible SUI layout, navigation, settings and rendering |
| `keepOnScreen` | 14333 | Accessible SUI layout, navigation, settings and rendering |
| `makeDraggable` | 14348 | Accessible SUI layout, navigation, settings and rendering |
| `makeResizable` | 14387 | Accessible SUI layout, navigation, settings and rendering |
| `lift` | 14447 | Accessible SUI layout, navigation, settings and rendering |
| `focus` | 14449 | Accessible SUI layout, navigation, settings and rendering |
| `teardown` | 14458 | Accessible SUI layout, navigation, settings and rendering |
| `close` | 14465 | Accessible SUI layout, navigation, settings and rendering |
| `minimize` | 14489 | Accessible SUI layout, navigation, settings and rendering |
| `restore` | 14513 | Accessible SUI layout, navigation, settings and rendering |
| `closeTop` | 14528 | Accessible SUI layout, navigation, settings and rendering |
| `dockTargetPoint` | 14535 | Scoped analytics, management documents and exports |
| `paint` | 14542 | Accessible SUI layout, navigation, settings and rendering |
| `onScopeChange` | 14585 | Accessible SUI layout, navigation, settings and rendering |
| `rehydrate` | 14599 | Business calculations, financial assumptions and plan pricing |
| `toolGroup` | 14761 | Scoped analytics, management documents and exports |
| `downloadToolDoc` | 14823 | Scoped analytics, management documents and exports |
| `entryLabel` | 14861 | Accessible SUI layout, navigation, settings and rendering |
| `needsPricing` | 14864 | Business calculations, financial assumptions and plan pricing |
| `pricedEntries` | 14869 | Business calculations, financial assumptions and plan pricing |
| `priceableEntries` | 14877 | Business calculations, financial assumptions and plan pricing |
| `onMoneyPlanPick` | 14979 | Business calculations, financial assumptions and plan pricing |
| `previewMoney` | 15005 | Business calculations, financial assumptions and plan pricing |
| `moneyBreakdownHTML` | 15034 | Business calculations, financial assumptions and plan pricing |
| `saveMoney` | 15112 | Business calculations, financial assumptions and plan pricing |
| `hourlyRate` | 15143 | Business calculations, financial assumptions and plan pricing |
| `injectAdminSections` | 15145 | Accessible SUI layout, navigation, settings and rendering |
| `summaryRows` | 15311 | Scoped analytics, management documents and exports |
| `renderToolsSummary` | 15331 | Scoped analytics, management documents and exports |
| `stat` | 15403 | Accessible SUI layout, navigation, settings and rendering |
| `setFinanceTab` | 15411 | Business calculations, financial assumptions and plan pricing |
| `saveFinanceSettings` | 15416 | Business calculations, financial assumptions and plan pricing |
| `saveCompanySettings` | 15432 | Accessible SUI layout, navigation, settings and rendering |
| `renderCompany` | 15442 | Accessible SUI layout, navigation, settings and rendering |
| `toolPricingRows` | 15466 | Business calculations, financial assumptions and plan pricing |
| `onToolPlanPick` | 15588 | Business calculations, financial assumptions and plan pricing |
| `previewToolPricing` | 15607 | Business calculations, financial assumptions and plan pricing |
| `saveToolPricing` | 15635 | Business calculations, financial assumptions and plan pricing |
| `renderFinance` | 15662 | Business calculations, financial assumptions and plan pricing |
| `loadCalcFromTool` | 15733 | Business calculations, financial assumptions and plan pricing |
| `runCalc` | 15760 | Business calculations, financial assumptions and plan pricing |
| `row` | 15822 | Accessible SUI layout, navigation, settings and rendering |
| `verdictLine` | 15825 | Accessible SUI layout, navigation, settings and rendering |
| `evalExpression` | 15835 | Business calculations, financial assumptions and plan pricing |
| `expr` | 15843 | Business calculations, financial assumptions and plan pricing |
| `term` | 15848 | Business calculations, financial assumptions and plan pricing |
| `unary` | 15857 | Business calculations, financial assumptions and plan pricing |
| `atom` | 15862 | Business calculations, financial assumptions and plan pricing |
| `runScratch` | 15873 | Business calculations, financial assumptions and plan pricing |
| `saveNotify` | 15889 | Delivery, in-app notifications and admin outbox |
| `showWhatsAppStatus` | 15916 | Delivery, in-app notifications and admin outbox |
| `openWhatsAppWebhookSetup` | 15920 | Delivery, in-app notifications and admin outbox |
| `testWhatsAppEndpoint` | 15923 | Delivery, in-app notifications and admin outbox |
| `configPushNotifyDebounced` | 15943 | Delivery, in-app notifications and admin outbox |
| `testMailEndpoint` | 15964 | Delivery, in-app notifications and admin outbox |
| `renderNotify` | 15995 | Delivery, in-app notifications and admin outbox |
| `renderOutbox` | 16024 | Delivery, in-app notifications and admin outbox |
| `populateCalcPicker` | 16072 | Business calculations, financial assumptions and plan pricing |
| `dayStart` | 16102 | Scoped analytics, management documents and exports |
| `isoDay` | 16108 | Scoped analytics, management documents and exports |
| `rangeLabel` | 16115 | Scoped analytics, management documents and exports |
| `setExecPeriod` | 16125 | Scoped analytics, management documents and exports |
| `applyExecCustom` | 16147 | Scoped analytics, management documents and exports |
| `execCustomNote` | 16157 | Scoped analytics, management documents and exports |
| `execOption` | 16173 | Scoped analytics, management documents and exports |
| `execLaunchNote` | 16179 | Scoped analytics, management documents and exports |
| `openExecBriefing` | 16190 | Scoped analytics, management documents and exports |
| `execWindow` | 16210 | Scoped analytics, management documents and exports |
| `inWindow` | 16232 | Scoped analytics, management documents and exports |
| `execBars` | 16239 | Scoped analytics, management documents and exports |
| `execLine` | 16257 | Scoped analytics, management documents and exports |
| `execDonut` | 16277 | Scoped analytics, management documents and exports |
| `execBriefingModel` | 16310 | Scoped analytics, management documents and exports |
| `renderExecBriefing` | 16378 | Scoped analytics, management documents and exports |
| `execNarrative` | 16563 | Scoped analytics, management documents and exports |
| `execRecommendations` | 16579 | Scoped analytics, management documents and exports |
| `execBriefingText` | 16605 | Scoped analytics, management documents and exports |
| `copyExecBriefing` | 16645 | Scoped analytics, management documents and exports |
| `printExecBriefing` | 16658 | Scoped analytics, management documents and exports |
| `execDocBody` | 16678 | Scoped analytics, management documents and exports |
| `execDocHTML` | 16870 | Scoped analytics, management documents and exports |
| `execFindings` | 16877 | Scoped analytics, management documents and exports |
| `downloadExecDoc` | 16968 | Scoped analytics, management documents and exports |
| `xmlEsc` | 16978 | Accessible SUI layout, navigation, settings and rendering |
| `cell` | 16979 | Accessible SUI layout, navigation, settings and rendering |
| `sheet` | 16984 | Accessible SUI layout, navigation, settings and rendering |
| `execWorkbookModel` | 16997 | Scoped analytics, management documents and exports |
| `execWorkbookXML` | 17109 | Scoped analytics, management documents and exports |
| `downloadExecWorkbook` | 17136 | Scoped analytics, management documents and exports |
| `showSheet` | 17180 | Accessible SUI layout, navigation, settings and rendering |
| `sheetViewHTML` | 17185 | Accessible SUI layout, navigation, settings and rendering |
| `downloadExecCsv` | 17226 | Scoped analytics, management documents and exports |
| `moneyIsMine` | 17248 | Business calculations, financial assumptions and plan pricing |
| `wizardStepPlan` | 17257 | Typed declarations, wizards, project/media details and review |
| `costIsMine` | 17262 | Business calculations, financial assumptions and plan pricing |
| `planIndex` | 17263 | Business calculations, financial assumptions and plan pricing |
| `firstStep` | 17264 | Typed declarations, wizards, project/media details and review |
| `lastStep` | 17265 | Typed declarations, wizards, project/media details and review |
| `applyWizardScope` | 17269 | Typed declarations, wizards, project/media details and review |
| `gotoStep` | 17326 | Typed declarations, wizards, project/media details and review |
| `renderWizardProgress` | 17381 | Typed declarations, wizards, project/media details and review |
| `updateWizardFooter` | 17405 | Typed declarations, wizards, project/media details and review |
| `nextStep` | 17431 | Typed declarations, wizards, project/media details and review |
| `prevStep` | 17440 | Typed declarations, wizards, project/media details and review |
| `toolIsKnown` | 17468 | Canonical catalogue and historical registry |
| `syncRegistryToggle` | 17472 | Canonical catalogue and historical registry |
| `isDriveLink` | 17552 | Accessible SUI layout, navigation, settings and rendering |
| `driveFolderUrl` | 17556 | Accessible SUI layout, navigation, settings and rendering |
| `openDriveFolder` | 17560 | Accessible SUI layout, navigation, settings and rendering |
| `armDriveCatcher` | 17572 | Accessible SUI layout, navigation, settings and rendering |
| `projectById` | 17612 | Typed declarations, wizards, project/media details and review |
| `renderProjects` | 17614 | Typed declarations, wizards, project/media details and review |
| `addProject` | 17635 | Typed declarations, wizards, project/media details and review |
| `removeProject` | 17643 | Typed declarations, wizards, project/media details and review |
| `openProjectTile` | 17649 | Typed declarations, wizards, project/media details and review |
| `projectLinkHint` | 17700 | Typed declarations, wizards, project/media details and review |
| `syncDriveRow` | 17708 | Canonical SQLite APIs and read-only import/export |
| `expandDriveRow` | 17730 | Accessible SUI layout, navigation, settings and rendering |
| `pasteProjectLink` | 17741 | Typed declarations, wizards, project/media details and review |
| `onProjectLink` | 17760 | Typed declarations, wizards, project/media details and review |
| `mediaKind` | 17842 | Typed declarations, wizards, project/media details and review |
| `mediaViewerHTML` | 17888 | Typed declarations, wizards, project/media details and review |
| `deptProjects` | 17930 | Typed declarations, wizards, project/media details and review |
| `renderQuickStats` | 17932 | Scoped analytics, management documents and exports |
| `renderMyHistoryCard` | 17954 | Accessible SUI layout, navigation, settings and rendering |
| `renderDeptOverview` | 17973 | Scoped analytics, management documents and exports |
| `renderDeptExtra` | 18005 | Accessible SUI layout, navigation, settings and rendering |
| `setMyToolsTab` | 18104 | Accessible SUI layout, navigation, settings and rendering |
| `myToolsTabsHTML` | 18108 | Accessible SUI layout, navigation, settings and rendering |
| `editedTitle` | 18120 | Accessible SUI layout, navigation, settings and rendering |
| `renderToolsList` | 18126 | Scoped analytics, management documents and exports |
| `deptPromptKey` | 18217 | Accessible SUI layout, navigation, settings and rendering |
| `deptPromptAnswered` | 18221 | Accessible SUI layout, navigation, settings and rendering |
| `markDeptPromptAnswered` | 18224 | Accessible SUI layout, navigation, settings and rendering |
| `resetDeptPrompt` | 18228 | Accessible SUI layout, navigation, settings and rendering |
| `maybeShowDeptPrompt` | 18236 | Accessible SUI layout, navigation, settings and rendering |
| `hideDeptPrompt` | 18258 | Accessible SUI layout, navigation, settings and rendering |
| `deptPromptPick` | 18267 | Accessible SUI layout, navigation, settings and rendering |
| `dismissDeptPrompt` | 18275 | Accessible SUI layout, navigation, settings and rendering |
| `routeAfterSignIn` | 18309 | Identity, profiles and server roles |
| `askConfirm` | 18393 | Native installation and contextual help |
| `answerAsk` | 18415 | Native installation and contextual help |
| `guardWith` | 18458 | Accessible SUI layout, navigation, settings and rendering |
| `reqStatusLabel` | 18476 | Typed declarations, wizards, project/media details and review |
| `renderRequestsInbox` | 18478 | Accessible SUI layout, navigation, settings and rendering |
| `repStatusLabel` | 18537 | Typed declarations, wizards, project/media details and review |
| `reportEntries` | 18538 | Accessible SUI layout, navigation, settings and rendering |
| `entryMedia` | 18539 | Typed declarations, wizards, project/media details and review |
| `setReportStatus` | 18540 | Typed declarations, wizards, project/media details and review |
| `setReportNote` | 18548 | Typed declarations, wizards, project/media details and review |
| `renderReportsInbox` | 18556 | Accessible SUI layout, navigation, settings and rendering |
| `looksLikeTest` | 18632 | Isolated synthetic fixtures and governed archival |
| `renderManageSubmissions` | 18648 | Typed declarations, wizards, project/media details and review |
| `toggleManagePick` | 18708 | Isolated synthetic fixtures and governed archival |
| `pickAllManage` | 18716 | Isolated synthetic fixtures and governed archival |
| `renderManageBulk` | 18720 | Isolated synthetic fixtures and governed archival |
| `removeCheckedSubmissions` | 18735 | Typed declarations, wizards, project/media details and review |
| `applyReassign` | 18797 | Typed declarations, wizards, project/media details and review |
| `deleteSubmission` | 18813 | Typed declarations, wizards, project/media details and review |
| `renameRegistryTool` | 18826 | Canonical catalogue and historical registry |
| `editRegistryUrl` | 18827 | Canonical catalogue and historical registry |
| `saveRegistryEdit` | 18852 | Canonical catalogue and historical registry |
| `renderBusinessList` | 18874 | Scoped analytics, management documents and exports |
| `costIsMineFor` | 18979 | Business calculations, financial assumptions and plan pricing |
| `needsDecision` | 18984 | Typed declarations, wizards, project/media details and review |
| `renderWhoTold` | 19158 | Accessible SUI layout, navigation, settings and rendering |
| `decideBccList` | 19180 | Delivery, in-app notifications and admin outbox |
| `decide` | 19188 | Typed declarations, wizards, project/media details and review |
| `announce` | 19248 | Accessible SUI layout, navigation, settings and rendering |
| `resendSubmission` | 19308 | Delivery, in-app notifications and admin outbox |
| `scopedFindings` | 19325 | Scoped analytics, management documents and exports |
| `setAnalysisScope` | 19337 | Scoped analytics, management documents and exports |
| `renderAiFindings` | 19339 | Scoped analytics, management documents and exports |
| `openFinding` | 19385 | Scoped analytics, management documents and exports |
| `sectionTitleOf` | 19483 | Accessible SUI layout, navigation, settings and rendering |
| `filterStore` | 19492 | Scoped analytics, management documents and exports |
| `hoistAdminFilters` | 19502 | Scoped analytics, management documents and exports |
| `activeFilterCount` | 19514 | Scoped analytics, management documents and exports |
| `buildSectionHead` | 19521 | Accessible SUI layout, navigation, settings and rendering |
| `renderSectionHead` | 19534 | Accessible SUI layout, navigation, settings and rendering |
| `renderFilterStatus` | 19570 | Scoped analytics, management documents and exports |
| `adminGoBack` | 19574 | Accessible SUI layout, navigation, settings and rendering |
| `clearAdminFilters` | 19580 | Scoped analytics, management documents and exports |
| `paintFilterNote` | 19616 | Scoped analytics, management documents and exports |
| `businessNode` | 19654 | Scoped analytics, management documents and exports |
| `splitBusinessCase` | 19658 | Scoped analytics, management documents and exports |
| `renderBusinessStrip` | 19685 | Scoped analytics, management documents and exports |
| `docShell` | 19803 | Scoped analytics, management documents and exports |
| `saveFile` | 19809 | Accessible SUI layout, navigation, settings and rendering |
| `slug` | 19817 | Canonical catalogue and historical registry |
| `stamp` | 19818 | Accessible SUI layout, navigation, settings and rendering |
| `submissionDocBody` | 19826 | Typed declarations, wizards, project/media details and review |
| `submissionDocHTML` | 19967 | Typed declarations, wizards, project/media details and review |
| `downloadSubmissionDoc` | 19990 | Typed declarations, wizards, project/media details and review |
| `printSubmissionDoc` | 19997 | Typed declarations, wizards, project/media details and review |
| `openPrintWindow` | 20003 | Scoped analytics, management documents and exports |
| `notifySettings` | 20032 | Delivery, in-app notifications and admin outbox |
| `saveNotifySettings` | 20045 | Delivery, in-app notifications and admin outbox |
| `outbox` | 20047 | Delivery, in-app notifications and admin outbox |
| `saveOutbox` | 20048 | Delivery, in-app notifications and admin outbox |
| `adminRecipients` | 20050 | Delivery, in-app notifications and admin outbox |
| `visibleRecipients` | 20057 | Delivery, in-app notifications and admin outbox |
| `visibleBcc` | 20065 | Delivery, in-app notifications and admin outbox |
| `mailRuleFor` | 20073 | Delivery, in-app notifications and admin outbox |
| `trackerEntryUrl` | 20078 | Accessible SUI layout, navigation, settings and rendering |
| `entryFromUrl` | 20087 | Accessible SUI layout, navigation, settings and rendering |
| `openEntryFromUrl` | 20091 | Accessible SUI layout, navigation, settings and rendering |
| `mailBodyFor` | 20103 | Delivery, in-app notifications and admin outbox |
| `mailSubjectFor` | 20124 | Delivery, in-app notifications and admin outbox |
| `queueMail` | 20137 | Delivery, in-app notifications and admin outbox |
| `whatsappOutbox` | 20184 | Delivery, in-app notifications and admin outbox |
| `saveWhatsappOutbox` | 20185 | Delivery, in-app notifications and admin outbox |
| `normalisePhone` | 20186 | Accessible SUI layout, navigation, settings and rendering |
| `isValidWhatsAppNumber` | 20192 | Delivery, in-app notifications and admin outbox |
| `whatsappTextFor` | 20196 | Delivery, in-app notifications and admin outbox |
| `queueWhatsApp` | 20200 | Delivery, in-app notifications and admin outbox |
| `deliverWhatsApp` | 20215 | Delivery, in-app notifications and admin outbox |
| `readMailReply` | 20252 | Delivery, in-app notifications and admin outbox |
| `deliver` | 20271 | Accessible SUI layout, navigation, settings and rendering |
| `markMail` | 20307 | Delivery, in-app notifications and admin outbox |
| `openInMailClient` | 20316 | Delivery, in-app notifications and admin outbox |
| `retryMail` | 20329 | Delivery, in-app notifications and admin outbox |
| `notifSeenKey` | 20349 | Delivery, in-app notifications and admin outbox |
| `notifSeenAt` | 20350 | Delivery, in-app notifications and admin outbox |
| `markNotifSeen` | 20353 | Delivery, in-app notifications and admin outbox |
| `notifItems` | 20357 | Delivery, in-app notifications and admin outbox |
| `notifUnread` | 20407 | Delivery, in-app notifications and admin outbox |
| `paintBell` | 20411 | Accessible SUI layout, navigation, settings and rendering |
| `openNotifications` | 20424 | Delivery, in-app notifications and admin outbox |
| `browserNotifSignature` | 20430 | Delivery, in-app notifications and admin outbox |
| `maybeNotifyBrowser` | 20433 | Delivery, in-app notifications and admin outbox |
| `requestBrowserNotifications` | 20447 | Delivery, in-app notifications and admin outbox |
| `publicSeen` | 20509 | Delivery, in-app notifications and admin outbox |
| `savePublicSeen` | 20512 | Delivery, in-app notifications and admin outbox |
| `announcePublicRequests` | 20515 | Accessible SUI layout, navigation, settings and rendering |
| `scrub` | 20596 | Canonical SQLite APIs and read-only import/export |
| `isInstruction` | 20723 | Native installation and contextual help |
| `psStash` | 20761 | Accessible SUI layout, navigation, settings and rendering |
| `psGroupsFor` | 20771 | Accessible SUI layout, navigation, settings and rendering |
| `buildPsPanes` | 20775 | Accessible SUI layout, navigation, settings and rendering |
| `returnPsGroups` | 20816 | Accessible SUI layout, navigation, settings and rendering |
| `loadProfileFields` | 20858 | Identity, profiles and server roles |
| `openProfileTile` | 20870 | Identity, profiles and server roles |
| `openSettingsTile` | 20871 | Accessible SUI layout, navigation, settings and rendering |

## Detail builders

Anonymous `DECK.register` builders are additional UI surfaces, not named function declarations. Their content is handled in the functional matrix:
- `overview` — source line 14693; native record detail, project, review, settings, analytics or management view according to the functional matrix.
- `tool` — source line 14721; native record detail, project, review, settings, analytics or management view according to the functional matrix.
- `toolStory` — source line 14763; native record detail, project, review, settings, analytics or management view according to the functional matrix.
- `toolNumbers` — source line 14771; native record detail, project, review, settings, analytics or management view according to the functional matrix.
- `toolDepts` — source line 14789; native record detail, project, review, settings, analytics or management view according to the functional matrix.
- `toolUses` — source line 14800; native record detail, project, review, settings, analytics or management view according to the functional matrix.
- `toolSubs` — source line 14809; native record detail, project, review, settings, analytics or management view according to the functional matrix.
- `money` — source line 14882; native record detail, project, review, settings, analytics or management view according to the functional matrix.
- `toolPricing` — source line 15501; native record detail, project, review, settings, analytics or management view according to the functional matrix.
- `mail` — source line 16045; native record detail, project, review, settings, analytics or management view according to the functional matrix.
- `execdoc` — source line 16191; native record detail, project, review, settings, analytics or management view according to the functional matrix.
- `docview` — source line 17152; native record detail, project, review, settings, analytics or management view according to the functional matrix.
- `sheetview` — source line 17167; native record detail, project, review, settings, analytics or management view according to the functional matrix.
- `project` — source line 17651; native record detail, project, review, settings, analytics or management view according to the functional matrix.
- `saved` — source line 18360; native record detail, project, review, settings, analytics or management view according to the functional matrix.
- `ask` — source line 18402; native record detail, project, review, settings, analytics or management view according to the functional matrix.
- `reassign` — source line 18770; native record detail, project, review, settings, analytics or management view according to the functional matrix.
- `regedit` — source line 18829; native record detail, project, review, settings, analytics or management view according to the functional matrix.
- `entry` — source line 18905; native record detail, project, review, settings, analytics or management view according to the functional matrix.
- `entryCase` — source line 18990; native record detail, project, review, settings, analytics or management view according to the functional matrix.
- `entryEffort` — source line 19017; native record detail, project, review, settings, analytics or management view according to the functional matrix.
- `entryProjects` — source line 19040; native record detail, project, review, settings, analytics or management view according to the functional matrix.
- `decide` — source line 19080; native record detail, project, review, settings, analytics or management view according to the functional matrix.
- `entryDocs` — source line 19284; native record detail, project, review, settings, analytics or management view according to the functional matrix.
- `finding` — source line 19391; native record detail, project, review, settings, analytics or management view according to the functional matrix.
- `deptAnalysis` — source line 19417; native record detail, project, review, settings, analytics or management view according to the functional matrix.
- `filters` — source line 19589; native record detail, project, review, settings, analytics or management view according to the functional matrix.
- `businessPart` — source line 19707; native record detail, project, review, settings, analytics or management view according to the functional matrix.
- `sectionMap` — source line 19728; native record detail, project, review, settings, analytics or management view according to the functional matrix.
- `submissionDoc` — source line 19973; native record detail, project, review, settings, analytics or management view according to the functional matrix.
- `notifications` — source line 20453; native record detail, project, review, settings, analytics or management view according to the functional matrix.
- `profile` — source line 20821; native record detail, project, review, settings, analytics or management view according to the functional matrix.
- `settings` — source line 20838; native record detail, project, review, settings, analytics or management view according to the functional matrix.
