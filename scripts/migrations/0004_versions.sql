-- OPP-90 : la version du plugin que Maestro et le Monitor font tourner, notée par chacun en démarrant (`claim`, `run`).
-- La Scène la compare à la version installée. Une base d'avant : NULL, lu « inconnue ».
ALTER TABLE runtime ADD COLUMN maestro_version TEXT;   -- la version du plugin chargée par la session Maestro
ALTER TABLE runtime ADD COLUMN monitor_version TEXT;   -- la version du plugin chargée par le Monitor
