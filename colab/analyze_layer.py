import sqlite3
import torch
from tqdm import tqdm
import logging

logger = logging.getLogger(__name__)

def analyze_layer(layer, batch_size, num_bins, device, database_path):
    conn = None
    try:
        conn = sqlite3.connect(database_path, timeout=60)  # Set a timeout of 60 seconds
        layer_activations = []
        c = conn.cursor()

        c.execute("SELECT COUNT(*) FROM activations WHERE layer = ?", (layer,))
        total_rows = c.fetchone()[0]
        num_batches = (total_rows + batch_size - 1) // batch_size

        for batch in tqdm(range(num_batches), desc=f"Processing layer {layer}", unit="batch"):
            offset = batch * batch_size
            c.execute("SELECT activation FROM activations WHERE layer = ? LIMIT ? OFFSET ?",
                      (layer, batch_size, offset))
            batch_activations = [row[0] for row in c.fetchall()]
            layer_activations.extend(batch_activations)

        activations_tensor = torch.tensor(layer_activations, dtype=torch.float32).to(device)
        abs_activations = torch.abs(activations_tensor)
        mean_abs_activation = torch.mean(abs_activations)
        std_abs_activation = torch.std(abs_activations)

        threshold = mean_abs_activation + 2 * std_abs_activation

        hist = torch.histc(abs_activations, bins=num_bins, min=0, max=abs_activations.max())
        cum_hist = torch.cumsum(hist, dim=0) / abs_activations.numel()
        proportion_threshold = (cum_hist >= 0.95).nonzero(as_tuple=True)[0][0].item() / num_bins

        normalized_activations = (abs_activations - mean_abs_activation) / std_abs_activation
        high_activations = normalized_activations[normalized_activations >= proportion_threshold]
        proportion = high_activations.numel() / normalized_activations.numel()

        if proportion >= 0.05:
            return int(layer.split('_')[1])
        else:
            return None
    except Exception as e:
        logger.exception(f"Error processing layer {layer}: {str(e)}")
        return None
    finally:
        if conn:
            conn.close()

def analyze_layer_helper(args):
    layer, chunk_size, num_bins, device, database_path = args
    result = analyze_layer(layer, chunk_size, num_bins, device, database_path)
    return layer, result
