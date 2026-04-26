# Home Assistant Brand Registry Submission

Files prepared for a PR against [home-assistant/brands](https://github.com/home-assistant/brands).

## What's in this directory

```
custom_integrations/onekommafive/
  icon.png      # 256×256 (copied from custom_components/onekommafive/brand/icon.png)
  icon@2x.png   # 512×512 (upscaled from icon.png via `sips -Z 512`)
```

⚠️ **Quality caveat:** `icon@2x.png` was upscaled from the 256×256 source by `sips`. It will look slightly blurry compared with a true 512-rendered logo. If a higher-resolution source is available (vector file or 512×512 export), drop it in here as `icon@2x.png` before opening the PR.

## How to submit

1. Fork [home-assistant/brands](https://github.com/home-assistant/brands).
2. Copy this directory into the fork:
   ```bash
   cp -R brand-prep/custom_integrations/onekommafive \
       /path/to/brands-fork/custom_integrations/
   ```
3. Open a PR titled `Add 1KOMMA5° icon`.
4. PR description suggestion:
   ```
   Adds the icon for the [`onekommafive`](https://github.com/mrebbert/1komma5-ha)
   custom integration (1KOMMA5° Heartbeat). Available via HACS as a custom
   repository.

   - icon.png (256×256, RGBA)
   - icon@2x.png (512×512, RGBA)
   ```
5. Wait for review — usually within a few days.

## After the PR is merged

The icon will appear automatically in HA's "Add integration" dialog and elsewhere — no integration code change needed. We can drop the local `custom_components/onekommafive/brand/icon.png` once the brand registry version is live.
