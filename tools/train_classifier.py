#!/usr/bin/env python3
"""Train the supine/side/empty classifier and export it to TFLite.

Run on your Mac (needs the heavy extras):

    pip install -e ".[train]"
    python tools/train_classifier.py --dataset dataset --out models

Expects dataset/<supine|side|empty>/*.jpg from tools/label_frames.py.
Writes models/model.tflite + models/labels.txt - copy both to the Pi's
models/ directory.
"""

from __future__ import annotations

import argparse
from pathlib import Path

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def _count_images(directory: Path) -> int:
    return sum(1 for p in directory.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--dataset", default="dataset")
    ap.add_argument("--out", default="models")
    ap.add_argument("--image-size", type=int, default=96,
                    help="model input size (must match the detector expectations)")
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--epochs", type=int, default=15, help="head training epochs")
    ap.add_argument("--fine-tune-epochs", type=int, default=5)
    ap.add_argument("--seed", type=int, default=1337)
    args = ap.parse_args()

    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras import layers

    tf.keras.utils.set_random_seed(args.seed)
    img = args.image_size

    dataset_root = Path(args.dataset)
    if not dataset_root.is_dir():
        raise SystemExit(f"dataset directory not found: {dataset_root}")
    class_dirs = [d for d in sorted(dataset_root.iterdir()) if d.is_dir()]
    counts = {d.name: _count_images(d) for d in class_dirs}
    class_dirs = [d for d in class_dirs if counts[d.name] > 0]
    if len(class_dirs) < 2:
        raise SystemExit(
            f"need at least 2 classes with images, found: {counts} - "
            "label more nights with tools/label_frames.py first"
        )
    print("class counts:", {d.name: counts[d.name] for d in class_dirs})

    train_ds = keras.utils.image_dataset_from_directory(
        str(dataset_root), validation_split=0.2, subset="training", seed=args.seed,
        image_size=(img, img), batch_size=args.batch_size, label_mode="int",
    )
    val_ds = keras.utils.image_dataset_from_directory(
        str(dataset_root), validation_split=0.2, subset="validation", seed=args.seed,
        image_size=(img, img), batch_size=args.batch_size, label_mode="int",
    )
    class_names = train_ds.class_names
    print("class label order (labels.txt):", class_names)

    autotune = tf.data.AUTOTUNE
    train_ds = train_ds.cache().shuffle(512).prefetch(autotune)
    val_ds = val_ds.cache().prefetch(autotune)

    # Augmentation lives inside the model (inactive at inference) so the
    # exported TFLite graph stays identical to what the Pi will run.
    # No vertical flips: the camera orientation is fixed.
    augmentation = keras.Sequential(
        [
            layers.RandomFlip("horizontal"),
            layers.RandomRotation(0.05),
            layers.RandomBrightness(0.25),
            layers.RandomContrast(0.25),
        ],
        name="augmentation",
    )
    base = keras.applications.MobileNetV2(
        input_shape=(img, img, 3), alpha=0.35, include_top=False, weights="imagenet"
    )
    base.trainable = False

    inputs = keras.Input(shape=(img, img, 3))
    x = augmentation(inputs)
    x = keras.applications.mobilenet_v2.preprocess_input(x)
    x = base(x, training=False)
    x = layers.GlobalAveragePooling2D()(x)
    x = layers.Dropout(0.2)(x)
    outputs = layers.Dense(len(class_names), activation="softmax")(x)
    model = keras.Model(inputs, outputs)
    model.compile(
        optimizer=keras.optimizers.Adam(1e-3),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )

    stop = keras.callbacks.EarlyStopping(
        monitor="val_accuracy", patience=4, restore_best_weights=True
    )
    print("== training the head ==")
    model.fit(train_ds, validation_data=val_ds, epochs=args.epochs, callbacks=[stop])

    print("== fine-tuning the backbone ==")
    base.trainable = True
    model.compile(
        optimizer=keras.optimizers.Adam(1e-5),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )
    model.fit(train_ds, validation_data=val_ds, epochs=args.fine_tune_epochs,
              callbacks=[stop])

    tflite_model = tf.lite.TFLiteConverter.from_keras_model(model).convert()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "model.tflite").write_bytes(tflite_model)
    (out / "labels.txt").write_text("\n".join(class_names) + "\n")
    print(f"wrote {out / 'model.tflite'} ({len(tflite_model) / 1024:.0f} KiB)")
    print(f"wrote {out / 'labels.txt'}")
    print("next: copy models/ to the Pi and run  noro --source pi --detector tflite")


if __name__ == "__main__":
    main()
