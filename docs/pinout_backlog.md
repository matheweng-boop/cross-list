# Pinout backlog: Infineon and Chipanalog gate drivers

Owner, 22 Oct 2026: transcribe the pinouts so each part's output option (split output / Miller clamp / plain) is
known to the matching engine. Done by the daily update run, about 5 datasheets per run (docs/daily_update.md),
public datasheets only, polite access. Tick a line when its parts carry a `pinout` (and `pinout_source`) in the
data file named, in the same format as the other gate drivers there; note a blocked or missing datasheet instead.

163 parts, 49 datasheets.

- [ ] Chipanalog · `chipanalog_isolation.yaml` · datasheet: (none recorded: find the public datasheet) · CA-IS3211MCG
- [ ] Chipanalog · `chipanalog_isolation.yaml` · datasheet: CAIS3211CdatasheetVersion1.03cn20260715.pdf · CA-IS3211CVBJ, CA-IS3211CVCJ, CA-IS3211CVCU
- [ ] Chipanalog · `chipanalog_isolation.yaml` · datasheet: CAIS3211SCWGdatasheetVersion1.00en.pdf · CA-IS3211SCWG
- [ ] Chipanalog · `chipanalog_isolation.yaml` · datasheet: CAIS3211datasheetVersion1.09.pdf · CA-IS3211VBJ, CA-IS3211VCJ, CA-IS3211VBG, CA-IS3211VCG, CA-IS3211SBG, CA-IS3211SCG, CA-IS3211VBU, CA-IS3211VCU
- [ ] Chipanalog · `chipanalog_isolation.yaml` · datasheet: CAIS3212DatasheetVersion1.01cn20250819.pdf · CA-IS3212SBS, CA-IS3212VCS, CA-IS3212SCS, CA-IS3212TSCG, CA-IS3212SCG, CA-IS3212VCG, CA-IS3212MCG, CA-IS3212MCS
- [ ] Chipanalog · `chipanalog_isolation.yaml` · datasheet: CAIS3213DatasheetV1.0cn.pdf · CA-IS3213VCG, CA-IS3213MCG
- [ ] Chipanalog · `chipanalog_isolation.yaml` · datasheet: CAIS3214DatasheetVersion1.00cn20251110.pdf · CA-IS3214SBG, CA-IS3214MBG, CA-IS3214TSCG, CA-IS3214MCG
- [ ] Chipanalog · `chipanalog_isolation.yaml` · datasheet: CAIS32156xDatasheetV1.1cn20250116.pdf · CA-IS3215VNW
- [ ] Chipanalog · `chipanalog_isolation.yaml` · datasheet: CAIS32156xQ1datasheetVersion1.1cn20250519.pdf · CA-IS3215ENW-Q1, CA-IS3215SNW-Q1, CA-IS3215LNW-Q1, CA-IS3216SNW-Q1
- [ ] Chipanalog · `chipanalog_isolation.yaml` · datasheet: CAIS32178xQ1datasheetVersion1.01cn20260326.pdf · CA-IS3217CNW-Q1, CA-IS3217SNW-Q1, CA-IS3217ANW-Q1, CA-IS3217LNW-Q1
- [ ] Chipanalog · `chipanalog_isolation.yaml` · datasheet: CAIS32212xQ1datasheetVersion1.03.pdf · CA-IS3221CW-Q1, CA-IS3221BW-Q1, CA-IS3222CW-Q1, CA-IS3222BW-Q1, CA-IS3221CN-Q1, CA-IS3221BN-Q1, CA-IS3222CN-Q1, CA-IS3222BN-Q1
- [ ] Chipanalog · `chipanalog_isolation.yaml` · datasheet: CAIS32212xdatasheetVersion1.04.pdf · CA-IS3221BW, CA-IS3221CW, CA-IS3222CW, CA-IS3222BW, CA-IS3221AW, CA-IS3221AN, CA-IS3221BN
- [ ] Chipanalog · `chipanalog_isolation.yaml` · datasheet: CAIS3221CdatasheetVersion1.00cn20260508.pdf · CA-IS3221CBN, CA-IS3221CBW, CA-IS3221CAN, CA-IS3221CAW
- [ ] Infineon · `infineon_isolation.yaml` · datasheet: infineon-1ed020i12-b2-datasheet-en.pdf · 1ED020I12B2XUMA1
- [ ] Infineon · `infineon_isolation.yaml` · datasheet: infineon-1ed020i12-f2-datasheet-en.pdf · 1ED020I12F2XUMA1
- [ ] Infineon · `infineon_isolation.yaml` · datasheet: infineon-1ed312xmu12f-datasheet-en.pdf · 1ED3124MU12FXUMA1, 1ED3127MU12FXUMA1, 1ED3125MU12FXUMA1
- [ ] Infineon · `infineon_isolation.yaml` · datasheet: infineon-1ed314xmu12f1ed314xmc12h-datasheet-en.pdf · 1ED3141MU12FXUMA1, 1ED3140MU12FXUMA1, 1ED3142MU12FXUMA1, 1ED3141MC12HXUMA1, 1ED3143MC12HXUMA1, 1ED3142MC12HXUMA1, 1ED3144MC12HXUMA1, 1ED3145MC12HXUMA1
- [ ] Infineon · `infineon_isolation.yaml` · datasheet: infineon-1ed31xxmc12h-1ed-x3-compact-datasheet-en.pdf · 1ED3122MC12HXUMA1, 1ED3124MC12HXUMA1, 1ED3120MC12HXUMA1, 1ED3121MC12HXUMA1, 1ED3123MC12HXUMA1, 1ED3131MC12HXUMA1
- [ ] Infineon · `infineon_isolation.yaml` · datasheet: infineon-1ed31xxmu12h-datasheet-en.pdf · 1ED3124MU12HXUMA1, 1ED3120MU12HXUMA1, 1ED3121MU12HXUMA1, 1ED3122MU12HXUMA1, 1ED3123MU12HXUMA1, 1ED3131MU12HXUMA1
- [ ] Infineon · `infineon_isolation.yaml` · datasheet: infineon-1ed332xmc12n-datasheet-en.pdf · 1ED3321MC12NXUMA1, 1ED3320MC12NXUMA1, 1ED3322MC12NXUMA1, 1ED3323MC12NXUMA1
- [ ] Infineon · `infineon_isolation.yaml` · datasheet: infineon-1ed3330mc12m-datasheet-en.pdf · 1ED3330MC12MXUMA1
- [ ] Infineon · `infineon_isolation.yaml` · datasheet: infineon-1ed34x1mx12m-datasheet-en.pdf · 1ED3491MC12MXUMA1, 1ED3431MC12MXUMA1, 1ED3461MC12MXUMA1, 1ED3431MU12MXUMA1, 1ED3461MU12MXUMA1, 1ED3491MU12MXUMA1
- [ ] Infineon · `infineon_isolation.yaml` · datasheet: infineon-1ed38x0mx12m-datasheet-en.pdf · 1ED3890MC12MXUMA1, 1ED3830MC12MXUMA1, 1ED3860MC12MXUMA1, 1ED3830MU12MXUMA1, 1ED3860MU12MXUMA1, 1ED3890MU12MXUMA1
- [ ] Infineon · `infineon_isolation.yaml` · datasheet: infineon-1edcxxi12ah-datasheet-en.pdf · 1EDC20H12AHXUMA1, 1EDC20I12AHXUMA1, 1EDC40I12AHXUMA1, 1EDC60H12AHXUMA1, 1EDC60I12AHXUMA1
- [ ] Infineon · `infineon_isolation.yaml` · datasheet: infineon-1edcxxi12mh-datasheet-en.pdf · 1EDC20I12MHXUMA1, 1EDC30I12MHXUMA1
- [ ] Infineon · `infineon_isolation.yaml` · datasheet: infineon-1edixxi12mh-datasheet-en.pdf · 1EDI20I12MHXUMA1, 1EDI30I12MHXUMA1
- [ ] Infineon · `infineon_isolation.yaml` · datasheet: infineon-1edixxs12ff-datasheet-datasheet-en.pdf · 1EDI20I12MFXUMA1, 1EDI60I12AFXUMA1, 1EDI60N12AFXUMA1, 1EDI20I12AFXUMA1, 1EDI20N12AFXUMA1, 1EDI30I12MFXUMA1, 1EDI40I12AFXUMA1
- [ ] Infineon · `infineon_isolation.yaml` · datasheet: infineon-1edixxy12ah-datasheet-en.pdf · 1EDI20H12AHXUMA1, 1EDI20I12AHXUMA1, 1EDI60I12AHXUMA1, 1EDI40I12AHXUMA1, 1EDI60H12AHXUMA1
- [ ] Infineon · `infineon_isolation.yaml` · datasheet: infineon-2ed314xmc12l-datasheet-en.pdf · 2ED3140MC12LXUMA1, 2ED3141MC12LXUMA1, 2ED3142MC12LXUMA1, 2ED3143MC12LXUMA1, 2ED3144MC12LXUMA1, 2ED3145MC12LXUMA1, 2ED3146MC12LXUMA1, 2ED3147MC12LXUMA1
- [ ] Infineon · `infineon_isolation.yaml` · datasheet: infineon-2edb7259y-datasheet-en.pdf · 2EDB7259YXUMA1
- [ ] Infineon · `infineon_isolation.yaml` · datasheet: infineon-2edb8259f-datasheet-en.pdf · 2EDB8259FXUMA1
- [ ] Infineon · `infineon_isolation.yaml` · datasheet: infineon-2edb8259y-datasheet-en.pdf · 2EDB8259YXUMA1
- [ ] Infineon · `infineon_isolation.yaml` · datasheet: infineon-2edb9259y-datasheet-en.pdf · 2EDB9259YXUMA1
- [ ] Infineon · `infineon_isolation.yaml` · datasheet: infineon-2edf7175f-datasheet-en.pdf · 2EDF7175FXUMA2
- [ ] Infineon · `infineon_isolation.yaml` · datasheet: infineon-2edf7275f-datasheet-en.pdf · 2EDF7275FXUMA2
- [ ] Infineon · `infineon_isolation.yaml` · datasheet: infineon-2edf8275f-datasheet-en.pdf · 2EDF8275FXUMA1
- [ ] Infineon · `infineon_isolation.yaml` · datasheet: infineon-2edf9275f-datasheet-en.pdf · 2EDF9275FXUMA1
- [ ] Infineon · `infineon_isolation.yaml` · datasheet: infineon-2eds7165h-datasheet-en.pdf · 2EDS7165HXUMA1
- [ ] Infineon · `infineon_isolation.yaml` · datasheet: infineon-2eds8165h-datasheet-en.pdf · 2EDS8165HXUMA2
- [ ] Infineon · `infineon_isolation.yaml` · datasheet: infineon-2eds8265h-datasheet-en.pdf · 2EDS8265HXUMA2
- [ ] Infineon · `infineon_isolation.yaml` · datasheet: infineon-2eds9265h-datasheet-en.pdf · 2EDS9265HXUMA1
- [ ] Infineon · `infineon_isolation.yaml` · datasheet: infineon-eicedriver-1ed301xmc12i-opto-emulator-gate-driver-ic-datasheet-en.pdf · 1ED3010MC12IXUMA1, 1ED3011MC12IXUMA1, 1ED3012MC12IXUMA1
- [ ] Infineon · `infineon_isolation.yaml` · datasheet: infineon-eicedriver-1ed32xxmc12h-datasheet-en.pdf · 1ED3251MC12HXUMA1, 1ED3241MC12HXUMA1, 1ED3240MC12HXUMA1, 1ED3250MC12HXUMA1
- [ ] Infineon · `infineon_isolation.yaml` · datasheet: infineon-eicedriver-1edbx275f-datasheet-en-Z8F47139823.pdf · 1EDB7275FXUMA1
- [ ] Infineon · `infineon_isolation.yaml` · datasheet: infineon-eicedriver-1edbx275f-datasheet-en-Z8F47139825.pdf · 1EDB9275FXUMA1
- [ ] Infineon · `infineon_isolation.yaml` · datasheet: infineon-eicedriver-1edbx275f-datasheet-en-Z8F47172298.pdf · 1EDB6275FXUMA1
- [ ] Infineon · `infineon_isolation.yaml` · datasheet: infineon-eicedriver-1edbx275f-datasheet-en.pdf · 1EDB8275FXUMA1
- [ ] Infineon · `infineon_isolation.yaml` · datasheet: infineon-eicedriver-2edr314xxqe-datasheet-en-Z8F80949906.pdf · 2EDR3140XQEXUMA1, 2EDR3142XQEXUMA1, 2EDR3144XQEXUMA1, 2EDR3146XQEXUMA1, 2EDR3147XQEXUMA1, 2EDR3148XQEXUMA1, 2EDR3149XQEXUMA1
- [ ] Infineon · `infineon_isolation.yaml` · datasheet: infineon-eicedriver-2edr8259h-2edrx259x-2edrx258x-datasheet-en.pdf · 2EDR8258XXUMA1, 2EDR8259HXUMA1, 2EDR6258XXUMA1, 2EDR7259XXUMA1, 2EDR8259XXUMA1, 2EDR9258XXUMA1, 2EDR9259XXUMA1
