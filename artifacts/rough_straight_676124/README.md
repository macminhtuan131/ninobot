# Preserved rough straight-route model

676,124-step checkpoint and its saved training configuration, copied without changing the originals.

The actor was checked offline for compatibility with the new rough route curriculum: deterministic predictions match after transfer and the new critic remains fresh. No ROS control or training was started.

This archive preserves model weights and config. It does not include a snapshot of the original Gazebo terrain or prove performance on the current expanded map.

Use --init-model with this checkpoint and a NEW curriculum output directory to transfer the actor. --resume is for continuing an existing matching curriculum run.
